from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import MembershipStatus, TenantRole


class MembershipInviteRequest(BaseModel):
    """Request body for inviting a user to a Company (R2.6).

    The inviting user is taken from the authenticated request and recorded as
    ``invited_by`` by the service; it is never accepted from the client. The
    owning ``company_id`` is resolved from the path, so only the invitee
    ``user_id`` and the tenant ``role`` are supplied here.
    """

    user_id: UUID
    role: TenantRole = TenantRole.member


class MembershipRead(BaseModel):
    """Membership view returned by the invite/accept/suspend/list endpoints."""

    id: UUID
    user_id: UUID
    company_id: UUID
    role: TenantRole
    status: MembershipStatus
    invited_by: UUID | None = None

    model_config = ConfigDict(from_attributes=True)


class MyMembershipRead(BaseModel):
    """A company the authenticated user belongs to, shaped for the tenant switcher.

    Flattens the user's Membership joined with its Company so the frontend
    ``CompanyMembership`` context can be hydrated directly: ``id`` is the
    Company id (the tenant the user acts on behalf of), with the user's
    ``role``/``status`` in that company. Used by ``GET /users/me/memberships``.
    """

    id: UUID
    name: str
    slug: str
    market: str | None = None
    role: TenantRole
    status: MembershipStatus
    membership_id: UUID
