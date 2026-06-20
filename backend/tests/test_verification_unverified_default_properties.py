"""Property-based test for "new verifiable entities start unverified" (Property 6).

The production verifiable entities (:class:`app.models.company.Company`,
:class:`app.models.profile.Profile`, :class:`app.models.job.Job`) declare
``verification_status`` as a *native* Postgres enum with a Python-side
``default=VerificationState.unverified`` and a matching
``server_default='unverified'``. The native enum plus the surrounding
``JSONB`` / ``ARRAY`` / ``PGUUID`` columns cannot be materialised on SQLite, so
-- mirroring the convention used by ``test_external_refs_roundtrip_properties.py``
and ``test_single_live_profile_properties.py`` -- this test defines
SQLite-friendly stand-in models that carry the *identical* ``verification_status``
column declaration (same Python default, same server default). Creating a row
without specifying ``verification_status`` and reading it back from a fresh
session therefore exercises the real default-resolution path against an in-memory
database.

The test also asserts directly against the production model metadata that each
entity's ``verification_status`` column declares ``unverified`` as its default --
so the stand-in's default provably mirrors production rather than drifting.

"User identity" is named as a verifiable entity by Property 6, but the ``User``
model carries no ``verification_status`` column; user identity verification rides
the shared :mod:`app.services.verification` state machine. We therefore pin its
"starts unverified" guarantee to that state machine: ``unverified`` is the entry
state (no transition leads *into* it).

Validates: Requirements 1.5, 7.3
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.company import Company
from app.models.enums import VerificationState
from app.models.job import Job
from app.models.profile import Profile
from app.services.verification import ALLOWED_TRANSITIONS


class _Base(DeclarativeBase):
    pass


def _verification_status_column() -> Mapped[VerificationState]:
    """Reproduce the production ``verification_status`` column declaration.

    Same Python default and server default as Company/Profile/Job; only the
    enum is rendered non-native so it materialises on SQLite. If the production
    default ever changes, the metadata assertion below fails -- this stand-in is
    not allowed to silently diverge.
    """

    return mapped_column(
        sa.Enum(VerificationState, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=VerificationState.unverified,
        server_default=sa.text("'unverified'"),
    )


class _CompanyStandIn(_Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    verification_status: Mapped[VerificationState] = _verification_status_column()


class _ProfileStandIn(_Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    verification_status: Mapped[VerificationState] = _verification_status_column()


class _JobStandIn(_Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    verification_status: Mapped[VerificationState] = _verification_status_column()


# Maps a generated "entity kind" to (production model, stand-in model, required
# text field name). Every verifiable entity that carries a verification_status
# column is represented.
_ENTITY_KINDS = {
    "company": (Company, _CompanyStandIn, "name"),
    "profile": (Profile, _ProfileStandIn, "name"),
    "job": (Job, _JobStandIn, "title"),
}


def _build_session() -> tuple[Session, sa.Engine]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    _Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    return session_factory(), engine


# Printable-ASCII text for the entity's required name/title field; the value is
# irrelevant to the property (the default must hold for any new entity) but
# varying it exercises many distinct rows.
_text = st.text(alphabet=st.characters(min_codepoint=32, max_codepoint=126), min_size=1, max_size=48)

# A creation is a (kind, name) pair; a scenario is a non-empty sequence of them
# spanning the verifiable entity kinds in arbitrary order and multiplicity.
_creation = st.tuples(st.sampled_from(sorted(_ENTITY_KINDS)), _text)
_scenario = st.lists(_creation, min_size=1, max_size=24)


# Feature: multi-tenant-hiring-platform, Property 6: New verifiable entities start unverified
@settings(max_examples=100, deadline=None)
@given(scenario=_scenario)
def test_new_verifiable_entities_start_unverified(scenario: list[tuple[str, str]]) -> None:
    """For any newly created Company / Profile / Job publication, the entity's
    verification state defaults to ``unverified`` -- without the creator ever
    specifying it.

    Each creation persists a stand-in row that carries the production
    ``verification_status`` default declaration, then reloads it from a fresh
    session to confirm the stored default resolves to ``VerificationState.unverified``.

    Validates: Requirements 1.5, 7.3
    """

    db, engine = _build_session()
    try:
        created: list[tuple[type, int]] = []
        for kind, label in scenario:
            _production, standin, field = _ENTITY_KINDS[kind]
            # Deliberately omit verification_status: the default must supply it.
            entity = standin(**{field: label})
            db.add(entity)
            db.commit()

            # In-memory ORM view already reflects the resolved default.
            assert entity.verification_status is VerificationState.unverified
            created.append((standin, entity.id))

        # Reload every created row from a clean session: the value read back from
        # the database alone is still unverified.
        db.expire_all()
        for standin, entity_id in created:
            reloaded = db.get(standin, entity_id)
            assert reloaded is not None
            assert reloaded.verification_status is VerificationState.unverified
    finally:
        db.close()
        engine.dispose()


# Feature: multi-tenant-hiring-platform, Property 6: New verifiable entities start unverified
@pytest.mark.parametrize("model", [Company, Profile, Job], ids=lambda m: m.__name__)
def test_production_verification_status_default_is_unverified(model: type) -> None:
    """The stand-in's default provably mirrors production: each production model's
    ``verification_status`` column declares ``unverified`` as both its Python and
    server default.

    Validates: Requirements 1.5, 7.3
    """

    column = model.__table__.columns["verification_status"]

    assert column.default is not None, f"{model.__name__}.verification_status has no Python default"
    assert column.default.arg is VerificationState.unverified, (
        f"{model.__name__}.verification_status default should be unverified, got {column.default.arg!r}"
    )
    assert column.nullable is False, f"{model.__name__}.verification_status should be NOT NULL"
    assert column.server_default is not None, f"{model.__name__}.verification_status has no server default"
    assert "unverified" in str(column.server_default.arg.text), (
        f"{model.__name__}.verification_status server default should be 'unverified'"
    )


# Feature: multi-tenant-hiring-platform, Property 6: New verifiable entities start unverified
def test_user_identity_verification_starts_unverified() -> None:
    """User identity verification carries no dedicated column; it rides the shared
    verification state machine. ``unverified`` is that machine's entry state: no
    transition leads *into* it, so a freshly created identity necessarily begins
    unverified.

    Validates: Requirements 1.5, 7.3
    """

    inbound_targets = {target for targets in ALLOWED_TRANSITIONS.values() for target in targets}
    assert VerificationState.unverified not in inbound_targets
    assert VerificationState.unverified in ALLOWED_TRANSITIONS


if __name__ == "__main__":  # pragma: no cover - convenience for ad-hoc runs
    pytest.main([__file__, "-v"])
