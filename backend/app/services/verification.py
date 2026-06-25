"""Per-entity verification state machine (DD-4, R7).

A single :data:`ALLOWED_TRANSITIONS` table and one :func:`transition` function
serve every verifiable entity (Company, User identity, Profile, Job publication)
rather than four bespoke flows. A transition validates that the target state is
reachable from the entity's current ``verification_status``, applies it,
reconciles trust badges, and writes exactly one ``AuditLog`` row — all within the
caller's transaction (DD-10: synchronous ``Session``; we flush, never commit).

Illegal transitions raise :class:`IllegalTransitionError` (mapped to ``409``) and
make no state change or audit write — the transition is atomic (R7 error path).
"""

from __future__ import annotations

from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.models.enums import VerificationState
from app.models.user import User
from app.services.audit import write_audit


class _Verifiable(Protocol):
    """Structural type for any entity carrying a verification state."""

    id: Any
    verification_status: VerificationState


class IllegalTransitionError(Exception):
    """Raised when a verification transition is not permitted (mapped to 409).

    The state machine rejects any transition not present in
    :data:`ALLOWED_TRANSITIONS`; the entity's state is left unchanged and no
    audit row is written.
    """

    def __init__(self, current: VerificationState, target: VerificationState) -> None:
        self.current = current
        self.target = target
        super().__init__(f"Illegal verification transition: {current.value} -> {target.value}")


# Verification state machine (DD-4, mirrors the design diagram). Each key maps to
# the set of states reachable from it in a single transition.
ALLOWED_TRANSITIONS: dict[VerificationState, set[VerificationState]] = {
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


def is_allowed(current: VerificationState, target: VerificationState) -> bool:
    """Return ``True`` if ``current -> target`` is a permitted transition."""
    return target in ALLOWED_TRANSITIONS.get(current, set())


def _reconcile_badges(db: Session, entity: _Verifiable) -> None:
    """Recompute trust badges after a state change.

    The trust service (task 5.4) may not be present yet; import it lazily and
    skip gracefully if unavailable so this module does not hard-depend on it.
    """
    try:
        from app.services.trust import reconcile_badges
    except ImportError:
        return
    reconcile_badges(db, entity)


def transition(
    db: Session,
    *,
    entity: _Verifiable,
    target_state: VerificationState,
    actor: User,
    reason: str | None = None,
) -> None:
    """Validate, apply, reconcile, and audit a verification transition (R7.4-7.9).

    Validates that ``target_state`` is reachable from the entity's current
    ``verification_status``. On an illegal transition, raises
    :class:`IllegalTransitionError` with no state change and no audit write. On a
    valid transition, sets the new state, reconciles trust badges (R8.5/8.6), and
    writes exactly one ``AuditLog`` row (R7.9).

    The work happens within the caller's transaction — :func:`write_audit`
    flushes but does not commit, so the whole transition is atomic.
    """
    current = entity.verification_status
    if not is_allowed(current, target_state):
        raise IllegalTransitionError(current, target_state)

    entity.verification_status = target_state

    # Recompute badges first so the audit `after` snapshot reflects the entity's
    # post-transition condition state where the trust service is available.
    _reconcile_badges(db, entity)

    after: dict[str, Any] = {"verification_status": target_state.value}
    if reason is not None:
        after["reason"] = reason

    write_audit(
        db,
        actor=actor,
        action="verification.transition",
        target_type=entity.__class__.__name__,
        target_id=entity.id,
        before={"verification_status": current.value},
        after=after,
    )
