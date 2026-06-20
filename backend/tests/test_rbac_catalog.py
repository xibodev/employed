"""Example tests for the RBAC permission/role catalog (R5.1, R5.2, R5.4).

These are straightforward assertions over the static catalog data in
``app.services.rbac`` — that the platform/tenant roles are defined and that the
required catalog permissions are present and self-consistent.
"""

from __future__ import annotations

from app.models.enums import PlatformRole, TenantRole
from app.services.rbac import (
    PERMISSION_CATALOG,
    PLATFORM_ROLE_PERMISSIONS,
    TENANT_ROLE_PERMISSIONS,
)

# Permissions the catalog MUST contain at minimum (R5.4).
REQUIRED_CATALOG_PERMISSIONS = {
    "job:moderate",
    "job:block",
    "job:unpublish",
    "job:mark_review",
    "job:verify",
    "company:verify",
    "profile:verify",
    "user:suspend",
    "platform_user:create",
    "platform_role:assign",
}


def test_platform_roles_are_defined() -> None:
    """PLATFORM_ROLE_PERMISSIONS defines every platform role (R5.1)."""
    assert set(PLATFORM_ROLE_PERMISSIONS) == {
        PlatformRole.platform_super_admin,
        PlatformRole.platform_moderator,
        PlatformRole.platform_support,
    }


def test_tenant_roles_are_defined() -> None:
    """TENANT_ROLE_PERMISSIONS defines every tenant role (R5.2)."""
    assert set(TENANT_ROLE_PERMISSIONS) == {
        TenantRole.org_owner,
        TenantRole.org_admin,
        TenantRole.recruiter,
        TenantRole.member,
    }


def test_catalog_contains_required_permissions() -> None:
    """The catalog includes at least the R5.4 moderation/platform permissions."""
    missing = REQUIRED_CATALOG_PERMISSIONS - set(PERMISSION_CATALOG)
    assert not missing, f"catalog missing required permissions: {sorted(missing)}"


def test_super_admin_holds_entire_catalog() -> None:
    """platform_super_admin bundles the full catalog (R5.1/R5.4)."""
    assert PLATFORM_ROLE_PERMISSIONS[PlatformRole.platform_super_admin] == PERMISSION_CATALOG


def test_role_bundle_permissions_are_in_catalog() -> None:
    """Every permission referenced by a role bundle is a catalog member (R5.4)."""
    for role, perms in PLATFORM_ROLE_PERMISSIONS.items():
        unknown = set(perms) - set(PERMISSION_CATALOG)
        assert not unknown, f"platform role {role} references unknown permissions: {sorted(unknown)}"

    for role, perms in TENANT_ROLE_PERMISSIONS.items():
        unknown = set(perms) - set(PERMISSION_CATALOG)
        assert not unknown, f"tenant role {role} references unknown permissions: {sorted(unknown)}"
