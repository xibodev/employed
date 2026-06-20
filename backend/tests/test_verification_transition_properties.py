"""Property-based tests for the verification state machine.

# Feature: multi-tenant-hiring-platform, Property 7: Verification transitions follow the state machine
"""

from __future__ import annotations

import builtins
from types import SimpleNamespace
from uuid import uuid4

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.models.audit_log import AuditLog
from app.models.enums import VerificationState
from app.services.verification import (
    ALLOWED_TRANSITIONS,
    IllegalTransitionError,
    transition,
)


class _FakeSession:
    """Minimal stand-in for a SQLAlchemy Session capturing add/flush calls."""

    def __init__(self) -> None:
        self.added: list[object] = []
        self.flushed = 0

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        self.flushed += 1


def _entity(state: VerificationState) -> SimpleNamespace:
    return SimpleNamespace(id=uuid4(), verification_status=state)


def _actor() -> SimpleNamespace:
    return SimpleNamespace(id=uuid4())


@pytest.fixture
def _no_trust_service(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the lazy trust-service import to fail so ``reconcile_badges`` is a no-op.

    ``transition`` imports ``app.services.trust`` lazily and tolerates its
    absence. Whether or not the trust service exists (task 5.4 may land in
    parallel), blocking the import keeps this property deterministic: a valid
    transition appends exactly one ``AuditLog`` row and nothing else.
    """
    real_import = builtins.__import__

    def _blocked_import(name: str, *args: object, **kwargs: object):
        if name == "app.services.trust":
            raise ImportError("trust service blocked for property isolation")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocked_import)


# Cartesian product of every (current, target) pair across all states.
_STATES = st.sampled_from(list(VerificationState))


@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(current=_STATES, target=_STATES)
def test_verification_transition_follows_state_machine(
    _no_trust_service: None,
    current: VerificationState,
    target: VerificationState,
) -> None:
    """Validates: Requirements 7.4, 7.5, 7.6, 7.7, 7.8, 10.1, 11.3, 11.4, 11.5, 11.6.

    For any starting state and any target state:
    - if ``target`` is reachable from ``current``, the entity's
      ``verification_status`` becomes ``target`` and exactly one audit row is
      appended;
    - otherwise ``IllegalTransitionError`` is raised, the state is unchanged, and
      no audit row is appended.
    """
    db = _FakeSession()
    entity = _entity(current)
    actor = _actor()

    is_allowed = target in ALLOWED_TRANSITIONS.get(current, set())

    if is_allowed:
        transition(db, entity=entity, target_state=target, actor=actor)

        assert entity.verification_status is target
        audit_rows = [obj for obj in db.added if isinstance(obj, AuditLog)]
        assert len(audit_rows) == 1
        entry = audit_rows[0]
        assert entry.action == "verification.transition"
        assert entry.before == {"verification_status": current.value}
        assert entry.after == {"verification_status": target.value}
        assert db.flushed == 1
    else:
        with pytest.raises(IllegalTransitionError):
            transition(db, entity=entity, target_state=target, actor=actor)

        # Atomic rejection: no state change and no audit row appended.
        assert entity.verification_status is current
        assert [obj for obj in db.added if isinstance(obj, AuditLog)] == []
        assert db.flushed == 0
