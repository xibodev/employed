"""Property-based test for "external_refs round-trips without migration" (Property 14).

The production entities (Company, Job, Profile, User, Application) declare
``external_refs`` as ``MutableDict.as_mutable(JSONB)`` -- a Postgres-only type
that cannot be materialised on SQLite. So, mirroring the convention used by
``test_single_live_profile_properties.py`` / ``test_rbac_properties.py``, this
test defines a SQLite-friendly stand-in entity that carries an ``external_refs``
column declared as ``MutableDict.as_mutable(JSON)``. The real
:mod:`app.services.external_refs` read/write helpers therefore execute for real
against an in-memory database.

The property: for any JSON-serialisable mapping written via ``set_external_ref``,
reloading the entity in a fresh session yields an equal mapping -- a plain JSONB
write, never a schema migration (R19.2).
"""

from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import create_engine
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from app.services.external_refs import (
    delete_external_ref,
    get_external_ref,
    get_external_refs,
    set_external_ref,
)


class _Base(DeclarativeBase):
    pass


class _Entity(_Base):
    """SQLite-friendly stand-in for any entity carrying an ``external_refs`` map.

    The single ``external_refs`` column reproduces the production declaration
    (``MutableDict.as_mutable`` over a JSON type) so the service's in-place
    dirty-tracking write path runs for real -- no DDL change is needed to store
    a new external identifier.
    """

    __tablename__ = "entities"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    external_refs: Mapped[dict[str, Any] | None] = mapped_column(MutableDict.as_mutable(sa.JSON))


def _build_engine() -> sa.Engine:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    _Base.metadata.create_all(engine)
    return engine


def _session_factory(engine: sa.Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


# System keys are short identifiers (e.g. "stripe", "greenhouse"); values are any
# JSON-serialisable scalar/structure. Printable ASCII keeps generated text clear
# of surrogate/encoding edge cases unrelated to the round-trip property.
_text = st.text(alphabet=st.characters(min_codepoint=32, max_codepoint=126), max_size=24)
_system_key = st.text(alphabet=st.characters(min_codepoint=33, max_codepoint=126), min_size=1, max_size=32)
_json_value = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False, allow_infinity=False) | _text,
    lambda children: st.lists(children, max_size=4) | st.dictionaries(_text, children, max_size=4),
    max_leaves=8,
)
_refs_mapping = st.dictionaries(_system_key, _json_value, max_size=8)


# Feature: multi-tenant-hiring-platform, Property 14: external_refs round-trips without migration
@settings(max_examples=100, deadline=None)
@given(refs=_refs_mapping)
def test_external_refs_round_trips_without_migration(refs: dict[str, Any]) -> None:
    """For any JSON-serialisable mapping written via ``set_external_ref``, the
    reloaded entity yields an equal mapping, with no schema change required.

    Validates: Requirements 19.2
    """

    engine = _build_engine()
    Session_ = _session_factory(engine)
    try:
        # Write phase: materialise an entity and set each generated key/value.
        write_db = Session_()
        entity = _Entity()
        write_db.add(entity)
        write_db.commit()
        entity_id = entity.id

        for system, value in refs.items():
            set_external_ref(write_db, entity, system, value)

        # The in-memory view already matches what we wrote.
        assert get_external_refs(entity) == refs
        write_db.close()

        # Reload phase: a fresh session reads back from the database alone.
        read_db = Session_()
        reloaded = read_db.get(_Entity, entity_id)
        assert reloaded is not None
        assert get_external_refs(reloaded) == refs
        for system, value in refs.items():
            assert get_external_ref(reloaded, system) == value
        read_db.close()
    finally:
        engine.dispose()


# Feature: multi-tenant-hiring-platform, Property 14: external_refs round-trips without migration
@settings(max_examples=100, deadline=None)
@given(refs=_refs_mapping, extra_key=_system_key)
def test_delete_external_ref_is_idempotent(refs: dict[str, Any], extra_key: str) -> None:
    """Deleting a system is idempotent: removing a present key drops exactly that
    key, and deleting an absent key is a no-op that still round-trips.

    Validates: Requirements 19.2
    """

    engine = _build_engine()
    Session_ = _session_factory(engine)
    try:
        write_db = Session_()
        entity = _Entity()
        write_db.add(entity)
        write_db.commit()
        entity_id = entity.id

        for system, value in refs.items():
            set_external_ref(write_db, entity, system, value)

        # Deleting a key not present is a no-op (idempotent on absence).
        if extra_key not in refs:
            delete_external_ref(write_db, entity, extra_key)
            assert get_external_refs(entity) == refs

        # Delete each present key; a second delete of the same key is a no-op.
        expected = dict(refs)
        for system in list(refs.keys()):
            delete_external_ref(write_db, entity, system)
            delete_external_ref(write_db, entity, system)
            expected.pop(system, None)
            assert get_external_refs(entity) == expected
        write_db.close()

        # The emptied mapping round-trips from a fresh session.
        read_db = Session_()
        reloaded = read_db.get(_Entity, entity_id)
        assert reloaded is not None
        assert get_external_refs(reloaded) == {}
        read_db.close()
    finally:
        engine.dispose()


if __name__ == "__main__":  # pragma: no cover - convenience for ad-hoc runs
    pytest.main([__file__, "-v"])
