from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import event

from app.models.audit_log import AuditLog
from app.models.profile_version import ProfileVersion
from app.services import audit


class _FakeSession:
    """Minimal stand-in for a SQLAlchemy Session capturing add/flush calls."""

    def __init__(self) -> None:
        self.added: list[object] = []
        self.flushed = 0

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        self.flushed += 1


def test_write_audit_records_user_actor() -> None:
    db = _FakeSession()
    actor = SimpleNamespace(id=uuid4())
    target_id = uuid4()

    entry = audit.write_audit(
        db,
        actor=actor,
        action="application.status_changed",
        target_type="application",
        target_id=target_id,
        before={"status": "applied"},
        after={"status": "reviewing"},
    )

    assert db.added == [entry]
    assert db.flushed == 1
    assert isinstance(entry, AuditLog)
    assert entry.actor_id == actor.id
    assert entry.actor_label is None
    assert entry.action == "application.status_changed"
    assert entry.target_type == "application"
    assert entry.target_id == target_id
    assert entry.before == {"status": "applied"}
    assert entry.after == {"status": "reviewing"}


def test_write_audit_records_system_actor_label() -> None:
    db = _FakeSession()
    target_id = uuid4()

    entry = audit.write_audit(
        db,
        actor=None,
        actor_label="worker:domain_verify",
        action="verification.transition",
        target_type="company",
        target_id=target_id,
    )

    assert entry.actor_id is None
    assert entry.actor_label == "worker:domain_verify"
    assert entry.before is None
    assert entry.after is None


def test_write_audit_requires_actor_or_label() -> None:
    db = _FakeSession()

    with pytest.raises(ValueError):
        audit.write_audit(
            db,
            actor=None,
            action="moderation.action",
            target_type="job",
            target_id=uuid4(),
        )

    assert db.added == []


@pytest.mark.parametrize("model", [AuditLog, ProfileVersion])
def test_before_update_guard_registered(model: type) -> None:
    assert event.contains(model, "before_update", audit._block_mutation)


@pytest.mark.parametrize("model", [AuditLog, ProfileVersion])
def test_block_mutation_raises(model: type) -> None:
    with pytest.raises(audit.ImmutableRecordError):
        audit._block_mutation(None, None, model())
