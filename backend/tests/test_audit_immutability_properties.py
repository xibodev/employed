"""Property-based tests for append-only immutability of audit/profile-version rows.

``AuditLog`` (R22.3) and ``ProfileVersion`` (R13.3/R13.4) are append-only: rows
are written once and never updated. ``app.services.audit`` reinforces this at
the ORM layer by registering a ``before_update`` guard (``_block_mutation``) on
both models that raises :class:`ImmutableRecordError` whenever a flush would
emit an UPDATE for an existing row.

Both models use Postgres-only column types (``JSONB``, ``UUID``) and the test
conftest does *not* swap in SQLite-friendly replacements for them, so these
rows cannot be round-tripped through the in-memory SQLite engine. Instead, as
``tests/test_audit_service.py`` does, the property exercises the guard directly:
over a wide range of hypothesis-generated field values, ``_block_mutation``
must *always* reject the mutation and must leave the target record's fields
byte-for-byte unchanged.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.models.audit_log import AuditLog
from app.models.profile_version import ProfileVersion
from app.services import audit
from app.services.audit import ImmutableRecordError

# JSON-compatible payloads matching the JSONB columns (before/after, json_resume).
_json_scalars = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(10**6), max_value=10**6),
    st.text(max_size=20),
)
_json_dicts = st.dictionaries(keys=st.text(max_size=12), values=_json_scalars, max_size=5)


def _audit_logs() -> st.SearchStrategy[AuditLog]:
    """Generate ``AuditLog`` instances spanning user/system actors and payloads."""
    return st.builds(
        AuditLog,
        actor_id=st.one_of(st.none(), st.builds(uuid4)),
        actor_label=st.one_of(st.none(), st.text(max_size=32)),
        action=st.text(max_size=32),
        target_type=st.text(max_size=32),
        target_id=st.builds(uuid4),
        before=st.one_of(st.none(), _json_dicts),
        after=st.one_of(st.none(), _json_dicts),
    )


def _profile_versions() -> st.SearchStrategy[ProfileVersion]:
    """Generate ``ProfileVersion`` snapshot instances."""
    return st.builds(
        ProfileVersion,
        profile_id=st.builds(uuid4),
        user_id=st.builds(uuid4),
        version_number=st.integers(min_value=1, max_value=10_000),
        json_resume=_json_dicts,
    )


# The attributes captured to prove a rejected mutation leaves the row unchanged.
_AUDIT_FIELDS = ("actor_id", "actor_label", "action", "target_type", "target_id", "before", "after")
_VERSION_FIELDS = ("profile_id", "user_id", "version_number", "json_resume")


def _snapshot(record: object, fields: tuple[str, ...]) -> dict[str, object]:
    return {name: getattr(record, name) for name in fields}


# Feature: multi-tenant-hiring-platform, Property 10: Audit and profile-version records are append-only and immutable
# Validates: Requirements 13.3, 13.4, 22.3
@settings(max_examples=100, deadline=None)
@given(records=st.lists(_audit_logs(), min_size=1, max_size=8), index=st.integers(min_value=0))
def test_audit_log_mutation_always_rejected(records: list[AuditLog], index: int) -> None:
    """Mutating any existing ``AuditLog`` row is rejected; priors stay unchanged.

    For an arbitrary sequence of appended audit rows, attempting to update one
    of them (modelled by firing the ``before_update`` guard) raises
    ``ImmutableRecordError`` and every record's fields remain identical.
    """
    target = records[index % len(records)]
    before_states = [_snapshot(record, _AUDIT_FIELDS) for record in records]

    with pytest.raises(ImmutableRecordError):
        audit._block_mutation(None, None, target)

    # The rejected mutation must not have altered the target or any prior row.
    after_states = [_snapshot(record, _AUDIT_FIELDS) for record in records]
    assert after_states == before_states


# Feature: multi-tenant-hiring-platform, Property 10: Audit and profile-version records are append-only and immutable
# Validates: Requirements 13.3, 13.4, 22.3
@settings(max_examples=100, deadline=None)
@given(records=st.lists(_profile_versions(), min_size=1, max_size=8), index=st.integers(min_value=0))
def test_profile_version_mutation_always_rejected(records: list[ProfileVersion], index: int) -> None:
    """Mutating any existing ``ProfileVersion`` snapshot is rejected; priors stay unchanged."""
    target = records[index % len(records)]
    before_states = [_snapshot(record, _VERSION_FIELDS) for record in records]

    with pytest.raises(ImmutableRecordError):
        audit._block_mutation(None, None, target)

    after_states = [_snapshot(record, _VERSION_FIELDS) for record in records]
    assert after_states == before_states


# Feature: multi-tenant-hiring-platform, Property 10: Audit and profile-version records are append-only and immutable
# Validates: Requirements 13.3, 13.4, 22.3
@pytest.mark.parametrize("model", [AuditLog, ProfileVersion])
def test_before_update_guard_is_registered(model: type) -> None:
    """The ORM-layer ``before_update`` guard is wired on both append-only models."""
    from sqlalchemy import event

    assert event.contains(model, "before_update", audit._block_mutation)
