"""Membership lifecycle service (R2.6-2.9, R3.2-3.5).

A ``Membership`` is the join row linking a ``User`` to a ``Company`` (R2.1/2.2),
carrying a tenant ``role`` and a ``status`` of ``invited``/``active``/``suspended``
(R2.3). This module owns the transitions through that lifecycle:

* **invite** — create an ``invited`` membership recording who invited the person
  (R2.6);
* **accept** — move an ``invited`` membership to ``active`` on success, leaving it
  ``invited`` if acceptance cannot complete (R2.7/2.8);
* **suspend** — move a membership to ``suspended`` (R2.9);
* **domain auto-membership** — idempotently link a user to a company whose
  verified email domain matches, updating an existing row rather than duplicating
  it and recording the action in the audit trail (R3.2-3.5).

The data layer is the synchronous ``Session`` (DD-10): every function flushes
within the caller's transaction and never commits, leaving commit/rollback
semantics to the request boundary. The ``UniqueConstraint(user_id, company_id)``
on ``memberships`` is the anchor that makes domain auto-membership update-not-
duplicate (R3.4).
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.enums import MembershipStatus, TenantRole
from app.models.membership import Membership
from app.models.user import User
from app.services.audit import write_audit

# System actor label recorded on the audit entry written when a domain
# auto-membership is created (R3.5). Domain auto-membership is not performed by
# an authenticated user, so the audit row carries a system ``actor_label`` rather
# than an ``actor_id`` (see ``app.services.audit.write_audit``).
_DOMAIN_AUTO_MEMBERSHIP_ACTOR = "system:domain_auto_membership"


class MembershipError(Exception):
    """Raised when a membership transition is invalid for the current status.

    Used to reject, for example, accepting a membership that is not ``invited``.
    Raising leaves the membership status unchanged.
    """


def invite_member(
    db: Session,
    *,
    company_id: UUID,
    user_id: UUID,
    role: TenantRole,
    invited_by: UUID,
) -> Membership:
    """Invite a user to a company, creating an ``invited`` membership (R2.6).

    The new ``Membership`` links *user_id* to *company_id* with the given *role*,
    starts in ``invited`` status, and records *invited_by* so the inviting user is
    captured. The row is flushed within the caller's transaction (DD-10); the
    caller owns the commit. Returns the persisted ``Membership``.
    """
    membership = Membership(
        user_id=user_id,
        company_id=company_id,
        role=role,
        status=MembershipStatus.invited,
        invited_by=invited_by,
    )
    db.add(membership)
    db.flush()
    return membership


def accept_invitation(
    db: Session,
    *,
    membership: Membership,
    on_accept: Callable[[Membership], None] | None = None,
) -> Membership:
    """Accept an invited membership, moving it to ``active`` on success (R2.7/2.8).

    Only an ``invited`` membership can be accepted; any other status raises
    :class:`MembershipError` and leaves the status unchanged.

    The status change (and any caller-supplied *on_accept* work that must complete
    for acceptance to count, e.g. linking related records) runs inside a
    ``SAVEPOINT``. If that work raises, the nested transaction is rolled back so
    nothing partial persists and the membership is restored to ``invited`` (R2.8)
    without poisoning the caller's outer transaction; the original error
    propagates. On success the membership is ``active`` (R2.7). Returns the
    membership.
    """
    if membership.status is not MembershipStatus.invited:
        raise MembershipError(f"only an invited membership can be accepted (status={membership.status.value})")

    try:
        with db.begin_nested():
            membership.status = MembershipStatus.active
            if on_accept is not None:
                on_accept(membership)
            db.flush()
    except (SQLAlchemyError, MembershipError):
        # The SAVEPOINT rolled back the active transition without poisoning the
        # caller's transaction; ensure the in-memory status reflects the
        # persisted ``invited`` value (R2.8) before re-raising.
        membership.status = MembershipStatus.invited
        raise

    return membership


def suspend_member(db: Session, *, membership: Membership) -> Membership:
    """Suspend a membership, setting its status to ``suspended`` (R2.9).

    A suspended membership grants none of its role's tenant permissions (R2.10);
    that denial lives in the RBAC service. This function only records the status
    transition and flushes within the caller's transaction (DD-10). Returns the
    membership.
    """
    membership.status = MembershipStatus.suspended
    db.add(membership)
    db.flush()
    return membership


def _auto_membership_status_for_existing(current: MembershipStatus) -> MembershipStatus:
    """Resolve the status an existing membership takes under the domain policy.

    Domain auto-membership is a low-trust, automatic link that requires manual
    approval before it grants access (R3.3). It therefore never overrides a
    deliberate human decision already recorded on an existing membership:

    * ``active`` — an approved member stays active (no demotion);
    * ``suspended`` — an explicit admin suspension is preserved (no silent
      reinstatement);
    * ``invited`` — already awaiting approval; unchanged.

    In every case the existing status is retained, keeping the policy idempotent
    (Property 15) while satisfying R3.4's "change rather than duplicate" — the
    membership is updated in place, never duplicated.
    """
    return current


def apply_domain_auto_membership(
    db: Session,
    *,
    company: Company,
    user: User,
    role: TenantRole = TenantRole.member,
) -> Membership:
    """Idempotently link *user* to *company* via the domain policy (R3.2-3.5).

    Looks up any existing membership for the ``(user, company)`` pair using the
    ``UniqueConstraint(user_id, company_id)`` invariant:

    * **No existing membership** — create one with the given *role* and status
      ``invited`` (R3.3), then write an append-only ``AuditLog`` entry recording
      the auto-membership (R3.5).
    * **Existing membership** — never create a duplicate (R3.4). The status is
      resolved by :func:`_auto_membership_status_for_existing` (which preserves
      the existing status), so repeated application is a no-op (Property 15).

    Flushes within the caller's transaction (DD-10). Returns the single
    ``Membership`` for the pair.
    """
    stmt = sa.select(Membership).where(Membership.user_id == user.id, Membership.company_id == company.id).limit(1)
    existing = db.execute(stmt).scalar_one_or_none()

    if existing is not None:
        # Update in place rather than inserting a duplicate (R3.4). The policy
        # preserves the existing status, so this is idempotent (Property 15).
        new_status = _auto_membership_status_for_existing(existing.status)
        if existing.status is not new_status:
            existing.status = new_status
            db.add(existing)
            db.flush()
        return existing

    membership = Membership(
        user_id=user.id,
        company_id=company.id,
        role=role,
        status=MembershipStatus.invited,
    )
    db.add(membership)
    db.flush()  # assign membership.id before recording it in the audit trail

    write_audit(
        db,
        actor=None,
        actor_label=_DOMAIN_AUTO_MEMBERSHIP_ACTOR,
        action="membership.domain_auto_created",
        target_type="membership",
        target_id=membership.id,
        before=None,
        after={
            "user_id": str(user.id),
            "company_id": str(company.id),
            "role": role.value,
            "status": membership.status.value,
        },
    )

    return membership
