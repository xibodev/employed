"""Append-only audit-trail writer and immutability guards (R22, R13.4).

Privileged, verification, and moderation actions are recorded as ``AuditLog``
rows. There is no update or delete path: the service exposes only an append
operation, and ``before_update`` guards on the append-only models raise to
reinforce immutability at the ORM layer (DD-9).

Follows the synchronous ``Session`` data-layer pattern (DD-10).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.profile_version import ProfileVersion
from app.models.user import User


class ImmutableRecordError(Exception):
    """Raised when an append-only record is mutated after creation.

    Guards ``AuditLog`` (R22.3) and ``ProfileVersion`` (R13.4), which are
    append-only and must never be updated.
    """


def write_audit(
    db: Session,
    *,
    actor: User | None,
    action: str,
    target_type: str,
    target_id: UUID,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    actor_label: str | None = None,
) -> AuditLog:
    """Append a single ``AuditLog`` row capturing a privileged action (R22.1/22.2).

    The actor is either an authenticated :class:`User` (recorded via
    ``actor_id``) or a system actor (``actor=None`` plus an ``actor_label`` such
    as ``"worker:domain_verify"``). At least one of ``actor`` or ``actor_label``
    must be supplied.

    The row is added and flushed but not committed; the caller controls the
    surrounding transaction.
    """
    if actor is None and not actor_label:
        raise ValueError("write_audit requires either an actor or an actor_label")

    entry = AuditLog(
        actor_id=actor.id if actor is not None else None,
        actor_label=actor_label,
        action=action,
        target_type=target_type,
        target_id=target_id,
        before=before,
        after=after,
    )
    db.add(entry)
    db.flush()
    return entry


def _block_mutation(_mapper, _connection, target: object) -> None:
    """``before_update`` listener that forbids mutating append-only rows."""
    raise ImmutableRecordError(f"{type(target).__name__} rows are append-only and cannot be modified")


# Reinforce append-only immutability at the ORM layer (DD-9). The service has
# no update path; these guards reject any in-place mutation that slips through.
event.listen(AuditLog, "before_update", _block_mutation)
event.listen(ProfileVersion, "before_update", _block_mutation)
