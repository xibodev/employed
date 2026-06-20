"""Property-based tests for tenant-scope resolution in the RBAC core.

These tests exercise :func:`app.services.rbac.effective_permissions` against a
real (in-memory SQLite) ``memberships`` table built from the production
``Membership`` model, so the tenant-permission lookup query is the same code
path used in production (DD-2).

The acting user is given **no platform roles**, so the effective permission set
equals exactly the tenant layer — isolating tenant-scope resolution from the
platform layer (Property 1 covers their union).
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.enums import MembershipStatus, TenantRole
from app.models.membership import Membership
from app.services.rbac import TENANT_ROLE_PERMISSIONS, effective_permissions, has_permission

TENANT_ROLES = list(TenantRole)
MEMBERSHIP_STATUSES = list(MembershipStatus)

# A membership spec is (role, status); `None` means "no membership in company".
MembershipSpec = tuple[TenantRole, MembershipStatus] | None


@st.composite
def _scenario(draw: st.DrawFn) -> tuple[list[UUID], dict[UUID, MembershipSpec], UUID]:
    """Generate a user's multi-company membership landscape and a target company.

    Produces a set of distinct companies, a (possibly absent) membership for each
    with an independently drawn role and status, and the company that owns the
    resource being authorized.
    """

    company_ids = draw(st.lists(st.uuids(), min_size=2, max_size=6, unique=True))
    memberships: dict[UUID, MembershipSpec] = {}
    for company_id in company_ids:
        if draw(st.booleans()):
            role = draw(st.sampled_from(TENANT_ROLES))
            status = draw(st.sampled_from(MEMBERSHIP_STATUSES))
            memberships[company_id] = (role, status)
        else:
            memberships[company_id] = None
    target = draw(st.sampled_from(company_ids))
    return company_ids, memberships, target


def _expected_tenant_permissions(spec: MembershipSpec) -> frozenset[str]:
    """The tenant permissions the owning-company membership should contribute.

    Only an ``active`` membership grants permissions; ``invited``/``suspended``
    (and absent) memberships grant none.
    """

    if spec is None:
        return frozenset()
    role, status = spec
    if status is not MembershipStatus.active:
        return frozenset()
    return TENANT_ROLE_PERMISSIONS[role]


def _build_session(memberships: dict[UUID, MembershipSpec], user_id: UUID) -> tuple[Session, object]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Membership.__table__.create(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    db = session_factory()
    for company_id, spec in memberships.items():
        if spec is None:
            continue
        role, status = spec
        db.add(Membership(id=uuid4(), user_id=user_id, company_id=company_id, role=role, status=status))
    db.commit()
    return db, engine


# Feature: multi-tenant-hiring-platform, Property 2: Tenant scope is resolved from the owning company
@settings(max_examples=100, deadline=None)
@given(scenario=_scenario())
def test_tenant_scope_resolved_from_owning_company(
    scenario: tuple[list[UUID], dict[UUID, MembershipSpec], UUID],
) -> None:
    """The tenant permissions used to authorize an action on a resource owned by
    company C are exactly those granted by the user's ACTIVE membership in C, and
    are unaffected by the user's memberships in any other company.

    Validates: Requirements 5.6, 5.7
    """

    _company_ids, memberships, target = scenario
    user_id = uuid4()
    db, engine = _build_session(memberships, user_id)
    try:
        # No platform roles ⇒ effective permissions == the tenant layer alone.
        user = SimpleNamespace(id=user_id, roles=[])

        resolved = effective_permissions(db, user, target)
        expected = _expected_tenant_permissions(memberships[target])

        # Scope is resolved from the owning company: the result is exactly the
        # owning-company membership's grant. Because `expected` is computed solely
        # from the target company's membership, this equality also proves the
        # result is unaffected by memberships in other companies (R5.6/5.7).
        assert resolved == expected

        # Cross-check via has_permission: every expected permission is granted and
        # no permission outside the owning-company grant leaks in.
        for permission in expected:
            assert has_permission(db, user, permission, target)
        for permission in TENANT_ROLE_PERMISSIONS[TenantRole.org_owner] - expected:
            assert not has_permission(db, user, permission, target)
    finally:
        db.close()
        engine.dispose()


# Feature: multi-tenant-hiring-platform, Property 2: Tenant scope is resolved from the owning company
@settings(max_examples=100, deadline=None)
@given(
    role_a=st.sampled_from(TENANT_ROLES),
    role_b=st.sampled_from(TENANT_ROLES),
    status_b=st.sampled_from(MEMBERSHIP_STATUSES),
)
def test_other_company_membership_does_not_alter_target_scope(
    role_a: TenantRole,
    role_b: TenantRole,
    status_b: MembershipStatus,
) -> None:
    """Adding/altering a membership in a different company never changes the
    permissions resolved for the target company.

    The user holds an ACTIVE membership in company A (role_a) and an arbitrary
    membership in company B (role_b/status_b). The permissions resolved for A
    must equal A's active-membership grant regardless of B.

    Validates: Requirements 5.6, 5.7
    """

    user_id = uuid4()
    company_a = uuid4()
    company_b = uuid4()
    memberships: dict[UUID, MembershipSpec] = {
        company_a: (role_a, MembershipStatus.active),
        company_b: (role_b, status_b),
    }
    db, engine = _build_session(memberships, user_id)
    try:
        user = SimpleNamespace(id=user_id, roles=[])
        resolved_a = effective_permissions(db, user, company_a)
        assert resolved_a == TENANT_ROLE_PERMISSIONS[role_a]
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":  # pragma: no cover - convenience for ad-hoc runs
    pytest.main([__file__, "-v"])
