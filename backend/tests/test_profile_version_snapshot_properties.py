"""Property-based test for profile-version snapshot fidelity.

Exercises ``app.services.profiles_versioning.save_version`` against many
generated JSON Resume documents to confirm that a saved version captures the
live profile's content at the moment of the save, and that the captured
snapshot is independent of subsequent edits to the live working copy.

The service only relies on a small slice of the SQLAlchemy ``Session`` API
(``add`` / ``flush`` / ``query(max).scalar()``), so we reuse the established
``_FakeSession`` / ``SimpleNamespace`` conventions from
``test_profiles_versioning`` rather than spinning up a real database.
"""

from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from app.models.profile_version import ProfileVersion
from app.services import profiles_versioning as pv


class _FakeQuery:
    def __init__(self, max_version: int | None) -> None:
        self._max = max_version

    def filter(self, *args: object, **kwargs: object) -> "_FakeQuery":
        return self

    def scalar(self) -> int | None:
        return self._max


class _FakeSession:
    """Minimal Session stand-in for save_version's add/flush/query(max) usage."""

    def __init__(self, existing_max: int | None = None) -> None:
        self.added: list[object] = []
        self.flushed = 0
        self._existing_max = existing_max

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        self.flushed += 1

    def query(self, *args: object) -> _FakeQuery:
        return _FakeQuery(self._existing_max)


# JSON scalar/leaf values that round-trip cleanly through deep copy + equality.
_json_scalars = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-1_000_000, max_value=1_000_000),
    st.floats(allow_nan=False, allow_infinity=False, width=32),
    st.text(max_size=20),
)


def _json_values() -> st.SearchStrategy[Any]:
    """Arbitrary nested JSON values (objects, arrays, scalars)."""
    return st.recursive(
        _json_scalars,
        lambda children: st.one_of(
            st.lists(children, max_size=4),
            st.dictionaries(st.text(max_size=10), children, max_size=4),
        ),
        max_leaves=15,
    )


def _basics_strategy() -> st.SearchStrategy[dict[str, Any]]:
    """A ``basics`` object whose recognised sub-fields keep their JSON shapes."""
    return st.fixed_dictionaries(
        {},
        optional={
            "name": st.text(max_size=20),
            "label": st.text(max_size=20),
            "email": st.text(max_size=20),
            "profiles": st.lists(st.dictionaries(st.text(max_size=8), _json_scalars, max_size=3), max_size=3),
            "location": st.dictionaries(st.text(max_size=8), _json_scalars, max_size=4),
        },
    )


_ARRAY_SECTIONS = (
    "work",
    "volunteer",
    "education",
    "awards",
    "certificates",
    "publications",
    "skills",
    "languages",
    "interests",
    "references",
    "projects",
)


def _json_resume_strategy() -> st.SearchStrategy[dict[str, Any]]:
    """Generate structurally valid JSON Resume documents (R13.5).

    Recognised object sections carry objects, recognised array sections carry
    arrays, and ``basics`` keeps its sub-field shapes — exactly the constraints
    ``validate_json_resume`` enforces. A handful of extra free-form keys exercise
    sections the validator does not police.
    """
    optional: dict[str, st.SearchStrategy[Any]] = {
        "basics": _basics_strategy(),
        "meta": st.dictionaries(st.text(max_size=10), _json_values(), max_size=4),
    }
    for section in _ARRAY_SECTIONS:
        optional[section] = st.lists(_json_values(), max_size=4)
    optional["x_custom"] = _json_values()
    return st.fixed_dictionaries({}, optional=optional)


# Feature: multi-tenant-hiring-platform, Property 11: Saving a profile version snapshots the live profile
# Validates: Requirements 13.2
@settings(max_examples=100, deadline=None)
@given(document=_json_resume_strategy(), existing_max=st.one_of(st.none(), st.integers(min_value=0, max_value=1000)))
def test_save_version_snapshots_live_profile(document: dict[str, Any], existing_max: int | None) -> None:
    """A saved version equals the live profile's content at save time, and the
    snapshot stays frozen against later mutations of the live working copy.

    ``document`` is set as the live profile's working copy before the save, so
    the expectation is captured as an independent deep copy taken *before*
    ``save_version`` runs. After the save we mutate the live copy and assert the
    snapshot is unchanged, proving the version is a true point-in-time capture.
    """
    db = _FakeSession(existing_max=existing_max)
    profile = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        json_resume=copy.deepcopy(document),
    )

    # The expected snapshot is the live content at the moment of the save.
    expected_snapshot = copy.deepcopy(document)

    version = pv.save_version(db, profile=profile)

    assert isinstance(version, ProfileVersion)
    # Fidelity: the version captures exactly the live content at save time.
    assert version.json_resume == expected_snapshot
    assert version.version_number == int(existing_max or 0) + 1

    # Independence: mutating the live working copy must not alter the snapshot.
    _mutate(profile.json_resume)
    assert version.json_resume == expected_snapshot


# Feature: multi-tenant-hiring-platform, Property 11: Saving a profile version snapshots the live profile
# Validates: Requirements 13.2
@settings(max_examples=100, deadline=None)
@given(document=_json_resume_strategy(), existing_max=st.one_of(st.none(), st.integers(min_value=0, max_value=1000)))
def test_save_version_snapshots_supplied_resume(document: dict[str, Any], existing_max: int | None) -> None:
    """When the new resume is supplied to ``save_version`` it becomes the live
    working copy and the version snapshots that same content."""
    db = _FakeSession(existing_max=existing_max)
    profile = SimpleNamespace(id=uuid4(), user_id=uuid4(), json_resume=None)

    expected_snapshot = copy.deepcopy(document)

    version = pv.save_version(db, profile=profile, json_resume=document)

    assert version.json_resume == expected_snapshot
    assert profile.json_resume == expected_snapshot

    # Snapshot independence from later live-copy edits.
    _mutate(profile.json_resume)
    assert version.json_resume == expected_snapshot


def _mutate(document: dict[str, Any]) -> None:
    """Apply an in-place edit to the live working copy after a save.

    Adds a sentinel key and, where present, perturbs a recognised section so the
    mutation reaches nested structures the snapshot must not share.
    """
    document["__mutated__"] = "changed-after-save"
    basics = document.get("basics")
    if isinstance(basics, dict):
        basics["name"] = "Mutated Name"
    work = document.get("work")
    if isinstance(work, list):
        work.append({"injected": True})
