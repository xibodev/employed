from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.audit_log import AuditLog
from app.models.enums import VerificationState
from app.services import verification
from app.services.verification import ALLOWED_TRANSITIONS, IllegalTransitionError, transition


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


def test_allowed_transitions_match_state_machine() -> None:
    assert ALLOWED_TRANSITIONS == {
        VerificationState.unverified: {VerificationState.pending, VerificationState.flagged},
        VerificationState.pending: {
            VerificationState.verified,
            VerificationState.rejected,
            VerificationState.flagged,
        },
        VerificationState.verified: {VerificationState.revoked, VerificationState.flagged},
        VerificationState.rejected: {VerificationState.pending},
        VerificationState.revoked: {VerificationState.pending},
        VerificationState.flagged: {VerificationState.pending},
    }


def test_transition_applies_state_and_writes_single_audit_row() -> None:
    db = _FakeSession()
    entity = _entity(VerificationState.pending)
    actor = _actor()

    transition(db, entity=entity, target_state=VerificationState.verified, actor=actor, reason="docs ok")

    assert entity.verification_status is VerificationState.verified
    # Exactly one audit row written (R7.9).
    audit_rows = [obj for obj in db.added if isinstance(obj, AuditLog)]
    assert len(audit_rows) == 1
    entry = audit_rows[0]
    assert entry.action == "verification.transition"
    assert entry.target_type == "SimpleNamespace"
    assert entry.target_id == entity.id
    assert entry.actor_id == actor.id
    assert entry.before == {"verification_status": "pending"}
    assert entry.after == {"verification_status": "verified", "reason": "docs ok"}
    assert db.flushed == 1


def test_transition_without_reason_omits_reason_key() -> None:
    db = _FakeSession()
    entity = _entity(VerificationState.unverified)

    transition(db, entity=entity, target_state=VerificationState.pending, actor=_actor())

    entry = next(obj for obj in db.added if isinstance(obj, AuditLog))
    assert entry.after == {"verification_status": "pending"}


def test_illegal_transition_raises_and_leaves_state_unchanged() -> None:
    db = _FakeSession()
    entity = _entity(VerificationState.unverified)

    with pytest.raises(IllegalTransitionError):
        transition(db, entity=entity, target_state=VerificationState.verified, actor=_actor())

    # No state change and no audit write — the transition is atomic.
    assert entity.verification_status is VerificationState.unverified
    assert db.added == []
    assert db.flushed == 0


def test_reconcile_badges_called_when_trust_service_available(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []
    fake_trust = SimpleNamespace(reconcile_badges=lambda db, entity: calls.append(entity))
    monkeypatch.setitem(__import__("sys").modules, "app.services.trust", fake_trust)

    db = _FakeSession()
    entity = _entity(VerificationState.pending)

    transition(db, entity=entity, target_state=VerificationState.rejected, actor=_actor())

    assert calls == [entity]


def test_reconcile_badges_skipped_gracefully_when_trust_service_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    real_import = builtins.__import__

    def _blocked_import(name: str, *args: object, **kwargs: object):
        if name == "app.services.trust":
            raise ImportError("trust service not implemented yet")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocked_import)

    db = _FakeSession()
    entity = _entity(VerificationState.verified)

    # Should not raise even though the trust service cannot be imported.
    transition(db, entity=entity, target_state=VerificationState.revoked, actor=_actor())

    assert entity.verification_status is VerificationState.revoked
    assert verification is not None  # module import sanity
