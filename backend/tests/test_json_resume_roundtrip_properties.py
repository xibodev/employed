"""Property-based test for JSON Resume storage→export round-tripping (Property 13).

The Platform stores a candidate's resume as a JSON Resume document on the live
``Profile`` and on immutable ``ProfileVersion`` snapshots, and exports it back out
via :func:`app.services.export.to_json_resume`. This module verifies the
round-trip is lossless: any valid JSON Resume document that is stored and then
loaded and exported comes back equal to the original.

To exercise the real serialize → persist → load boundary (R21.2) rather than just
in-memory object identity, generated documents are written through a JSON column
in an in-memory SQLite database and reloaded in a fresh session before export.
The production storing path (:func:`profiles_versioning.save_version`) is exercised
in tandem so both halves of the round-trip are real code.

Validates: Requirements 13.5, 18.1, 21.2
"""

from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import JSON, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from app.services import profiles_versioning as pv
from app.services.export import to_json_resume


class _Base(DeclarativeBase):
    pass


class _StoredResume(_Base):
    """Minimal record whose ``json_resume`` column persists a document as JSON.

    ``to_json_resume`` reads the ``json_resume`` attribute off whatever entity it
    is handed (Profile or ProfileVersion), so a single-column stand-in is enough
    to drive a genuine store→load→export round-trip through the JSON boundary.
    """

    __tablename__ = "stored_resumes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    json_resume: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class _FakeQuery:
    """Stand-in for ``save_version``'s ``query(max(version_number))`` lookup."""

    def filter(self, *args: object, **kwargs: object) -> "_FakeQuery":
        return self

    def scalar(self) -> int | None:
        return None


class _FakeSession:
    """Minimal Session for ``save_version``'s add/flush/query(max) usage."""

    def add(self, obj: object) -> None:  # pragma: no cover - trivial
        pass

    def flush(self) -> None:  # pragma: no cover - trivial
        pass

    def query(self, *args: object) -> _FakeQuery:
        return _FakeQuery()


# JSON-serializable scalar/recursive values: the building blocks of a resume.
# NaN/Infinity are excluded because they are not valid JSON; surrogate and null
# code points are excluded because they cannot survive the SQLite text boundary.
_safe_text = st.text(
    alphabet=st.characters(min_codepoint=1, blacklist_categories=("Cs",)),
    max_size=20,
)
_json_scalars = (
    st.none()
    | st.booleans()
    | st.integers(min_value=-(10**12), max_value=10**12)
    | st.floats(allow_nan=False, allow_infinity=False)
    | _safe_text
)
_json_values = st.recursive(
    _json_scalars,
    lambda children: (
        st.lists(children, max_size=4) | st.dictionaries(_safe_text, children, max_size=4)
    ),
    max_leaves=12,
)

# Object sections always carry string keys mapped to arbitrary JSON values.
_section_object = st.dictionaries(_safe_text, _json_values, max_size=4)
# Array sections (work/education/skills/...) are lists of such objects.
_section_array = st.lists(_section_object, max_size=4)
# `basics` uses the canonical field names plus the structurally-typed
# `location` (object) and `profiles` (array) the validator special-cases.
_BASICS_FIELDS = ("name", "label", "image", "email", "phone", "url", "summary")


@st.composite
def json_resume_documents(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a reasonably-shaped, structurally-valid JSON Resume document.

    Always includes a ``basics`` object (so the document is non-empty and thus
    truthy for the export path) and optionally adds the recognised array/object
    sections. The result always satisfies :func:`validate_json_resume`.
    """

    basics: dict[str, Any] = {}
    for field in _BASICS_FIELDS:
        if draw(st.booleans()):
            basics[field] = draw(_safe_text)
    if draw(st.booleans()):
        basics["location"] = draw(st.dictionaries(_safe_text, _json_values, max_size=4))
    if draw(st.booleans()):
        basics["profiles"] = draw(st.lists(_section_object, max_size=3))

    document: dict[str, Any] = {"basics": basics}

    for section in ("work", "education", "skills", "awards", "languages", "projects"):
        if draw(st.booleans()):
            document[section] = draw(_section_array)
    if draw(st.booleans()):
        document["meta"] = draw(_section_object)

    return document


def _store_and_load(document: dict[str, Any]) -> _StoredResume:
    """Persist *document* via a JSON column and reload it in a fresh session.

    Reloading from a new session forces the document to come back from its
    serialized form, so the assertion covers the real storage boundary.
    """

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    _Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    record_id = str(uuid4())

    writer: Session = session_factory()
    try:
        writer.add(_StoredResume(id=record_id, json_resume=document))
        writer.commit()
    finally:
        writer.close()

    reader: Session = session_factory()
    try:
        loaded = reader.get(_StoredResume, record_id)
        assert loaded is not None
        # Detach so the returned instance keeps its data after the session closes.
        reader.expunge(loaded)
        return loaded
    finally:
        reader.close()
        engine.dispose()


# Feature: multi-tenant-hiring-platform, Property 13: JSON Resume round-trips losslessly
@settings(max_examples=100, deadline=None)
@given(document=json_resume_documents())
def test_json_resume_round_trips_losslessly(document: dict[str, Any]) -> None:
    """For any valid JSON Resume document, storing it on a Profile/ProfileVersion
    and then loading and exporting it yields a document equal to the original.

    Validates: Requirements 13.5, 18.1, 21.2
    """

    # The generated document is a valid JSON Resume to begin with.
    assert pv.validate_json_resume(document) is document
    original = copy.deepcopy(document)

    # Path 1 — stored verbatim on a Profile-like record, then exported.
    loaded_profile = _store_and_load(document)
    assert to_json_resume(loaded_profile) == original

    # Path 2 — stored on an immutable ProfileVersion via the production
    # save_version path, then persisted/loaded and exported.
    profile = SimpleNamespace(id=uuid4(), user_id=uuid4(), json_resume=None)
    version = pv.save_version(_FakeSession(), profile=profile, json_resume=original)
    loaded_version = _store_and_load(dict(version.json_resume))
    assert to_json_resume(loaded_version) == original

    # The export must not hand back the live stored object (callers cannot mutate
    # ORM state through it), yet must compare equal — i.e. a faithful deep copy.
    exported = to_json_resume(loaded_profile)
    assert exported is not loaded_profile.json_resume


if __name__ == "__main__":  # pragma: no cover - convenience for ad-hoc runs
    pytest.main([__file__, "-v"])
