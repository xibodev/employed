"""Two-layer, permission-based RBAC core (DD-1/2/3).

Authorization always tests for a *permission* string (e.g. ``job:moderate``),
never a role name. Roles are static bundles of permissions resolved at check
time. A user's effective permissions are the union of:

* the permissions of every recognized platform role on ``user.roles`` (these act
  across all tenants), and
* the permissions granted by the user's **active** membership in the company that
  owns the target resource (``invited``/``suspended`` memberships grant none).

Either layer can authorize a tenant-scoped action on its own (DD-3).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, get_user_roles
from app.database import get_db
from app.models.enums import MembershipStatus, PlatformRole, TenantRole
from app.models.membership import Membership
from app.models.user import User

# --- Permission catalog (static data, DD-1) ----------------------------------
#
# Permissions are the atomic unit of authorization (R5.3). The catalog must
# contain at least the moderation/verification/platform permissions named in
# R5.4, plus the tenant-scoped permissions referenced by the job, membership,
# and application flows.

# Platform-scoped moderation & verification permissions (R5.4).
JOB_MODERATE = "job:moderate"
JOB_BLOCK = "job:block"
JOB_UNPUBLISH = "job:unpublish"
JOB_MARK_REVIEW = "job:mark_review"
JOB_VERIFY = "job:verify"
COMPANY_VERIFY = "company:verify"
PROFILE_VERIFY = "profile:verify"
USER_SUSPEND = "user:suspend"
PLATFORM_USER_CREATE = "platform_user:create"
PLATFORM_ROLE_ASSIGN = "platform_role:assign"

# Tenant-scoped permissions (referenced by jobs, memberships, applications).
JOB_POST = "job:post"
COMPANY_MANAGE = "company:manage"
COMPANY_MANAGE_MEMBERS = "company:manage_members"
COMPANY_VERIFY_DOMAIN = "company:verify_domain"
APPLICATION_REVIEW = "application:review"
APPLICATION_ADVANCE = "application:advance"

PERMISSION_CATALOG: frozenset[str] = frozenset(
    {
        # platform moderation / verification (R5.4)
        JOB_MODERATE,
        JOB_BLOCK,
        JOB_UNPUBLISH,
        JOB_MARK_REVIEW,
        JOB_VERIFY,
        COMPANY_VERIFY,
        PROFILE_VERIFY,
        USER_SUSPEND,
        PLATFORM_USER_CREATE,
        PLATFORM_ROLE_ASSIGN,
        # tenant-scoped
        JOB_POST,
        COMPANY_MANAGE,
        COMPANY_MANAGE_MEMBERS,
        COMPANY_VERIFY_DOMAIN,
        APPLICATION_REVIEW,
        APPLICATION_ADVANCE,
    }
)

# --- Role → permission bundles (static data, DD-1) ----------------------------

# Platform roles act across all tenants (R5.1).
PLATFORM_ROLE_PERMISSIONS: dict[PlatformRole, frozenset[str]] = {
    # super admin holds the entire catalog.
    PlatformRole.platform_super_admin: PERMISSION_CATALOG,
    # moderators handle marketplace trust: moderation + verification.
    PlatformRole.platform_moderator: frozenset(
        {
            JOB_MODERATE,
            JOB_BLOCK,
            JOB_UNPUBLISH,
            JOB_MARK_REVIEW,
            JOB_VERIFY,
            COMPANY_VERIFY,
            PROFILE_VERIFY,
            USER_SUSPEND,
        }
    ),
    # support staff have no privileged catalog actions by default.
    PlatformRole.platform_support: frozenset(),
}

# Tenant roles are scoped to a single company (R5.2).
TENANT_ROLE_PERMISSIONS: dict[TenantRole, frozenset[str]] = {
    TenantRole.org_owner: frozenset(
        {
            COMPANY_MANAGE,
            COMPANY_MANAGE_MEMBERS,
            COMPANY_VERIFY_DOMAIN,
            JOB_POST,
            APPLICATION_REVIEW,
            APPLICATION_ADVANCE,
        }
    ),
    TenantRole.org_admin: frozenset(
        {
            COMPANY_MANAGE_MEMBERS,
            COMPANY_VERIFY_DOMAIN,
            JOB_POST,
            APPLICATION_REVIEW,
            APPLICATION_ADVANCE,
        }
    ),
    TenantRole.recruiter: frozenset(
        {
            JOB_POST,
            APPLICATION_REVIEW,
            APPLICATION_ADVANCE,
        }
    ),
    # member/viewer is a read-only role with no privileged actions.
    TenantRole.member: frozenset(),
}


# --- Resolution helpers -------------------------------------------------------


def _platform_permissions(user: User) -> frozenset[str]:
    """Permissions granted by every recognized platform role on the user.

    Unknown / legacy role strings that do not map to a :class:`PlatformRole`
    are ignored here; legacy ``admin`` accounts are mapped to
    ``platform_super_admin`` by the RBAC migration (R6).
    """

    perms: set[str] = set()
    for role_name in get_user_roles(user):
        try:
            role = PlatformRole(role_name)
        except ValueError:
            continue
        perms |= PLATFORM_ROLE_PERMISSIONS.get(role, frozenset())
    return frozenset(perms)


def _tenant_permissions(db: Session, user: User, company_id: UUID) -> frozenset[str]:
    """Permissions granted by the user's ACTIVE membership in ``company_id``.

    Only an ``active`` membership contributes permissions; ``invited`` and
    ``suspended`` memberships grant none (R2.10).
    """

    membership = (
        db.query(Membership)
        .filter(
            Membership.user_id == user.id,
            Membership.company_id == company_id,
            Membership.status == MembershipStatus.active,
        )
        .first()
    )
    if membership is None:
        return frozenset()
    return TENANT_ROLE_PERMISSIONS.get(membership.role, frozenset())


def effective_permissions(db: Session, user: User, company_id: UUID | None) -> frozenset[str]:
    """Union of platform permissions (all tenants) and the tenant permissions
    granted by the user's active membership in ``company_id`` (DD-2/3).

    When ``company_id`` is ``None`` only platform permissions are returned.
    """

    perms = _platform_permissions(user)
    if company_id is not None:
        perms = perms | _tenant_permissions(db, user, company_id)
    return perms


def has_permission(
    db: Session,
    user: User,
    permission: str,
    company_id: UUID | None = None,
) -> bool:
    """True iff ``permission`` is in the user's effective permission set."""

    return permission in effective_permissions(db, user, company_id)


# --- FastAPI dependency factory -----------------------------------------------


def _coerce_uuid(value: object) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


async def _resolve_company_id(request: Request, param_name: str) -> UUID | None:
    """Resolve the owning company id from the target resource (DD-2).

    Looks at path params first, then query params, then the JSON request body.
    Returns ``None`` when no usable company id is present (a platform permission
    can still authorize the action).
    """

    raw = request.path_params.get(param_name)
    if raw is None:
        raw = request.query_params.get(param_name)
    if raw is None:
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001 - body may be absent or non-JSON
            body = None
        if isinstance(body, dict):
            raw = body.get(param_name)
    return _coerce_uuid(raw)


def require_permission(permission: str, *, tenant_param: str | None = None):
    """FastAPI dependency factory enforcing ``permission`` (DD-1/2/3).

    Resolves the owning ``company_id`` from the target resource using
    ``tenant_param`` (defaults to ``"company_id"``) and raises ``403`` when the
    permission is absent. The error detail is generic and never leaks which
    company or permission was missing.
    """

    param_name = tenant_param or "company_id"

    async def dependency(
        request: Request,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        company_id = await _resolve_company_id(request, param_name)
        if not has_permission(db, user, permission, company_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to perform this action",
            )
        return user

    return dependency
