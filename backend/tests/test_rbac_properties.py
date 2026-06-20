"""Property-based tests for the two-layer RBAC authorization core.

These exercise ``app.services.rbac`` across many generated combinations of
platform roles, tenant memberships (role + status), and required permissions.

The RBAC layer resolves a user's *active* tenant membership via a DB query
(``Membership.status == active``), so the test backs the check with a small
in-memory SQLite ``Membership`` model and points ``rbac.Membership`` at it. The
real WHERE-clause filtering (which is what makes invited/suspended memberships
contribute nothing) therefore executes for real, rather than being re-modelled
by a hand-rolled fake.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
import sqlalchemy as sa
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.enums import MembershipStatus, PlatformRole, TenantRole
from app.services import rbac
from app.services.rbac import (
    PERMISSION_CATALOG,
    PLATFORM_ROLE_PERMISSIONS,
    TENANT_ROLE_PERMISSIONS,
    effective_permissions,
    has_permission,
)


class _Base(DeclarativeBase):
    pass


class _Membership(_Base):
    """SQLite-friendly stand-in for ``app.models.membership.Membership``.

    Only the columns RBAC resolution reads are modelled. ``role`` / ``status``
    use SQLAlchemy ``Enum`` so reads return real enum members (matching the
    production model) and the ``status == active`` filter binds correctly.
    """

    __tablename__ = "memberships"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(sa.String(36), index=True)
    company_id: Mapped[str] = mapped_column(sa.String(36), index=True)
    role: Mapped[TenantRole] = mapped_column(sa.Enum(TenantRole, native_enum=False), nullable=False)
    status: Mapped[MembershipStatus] = mapped_column(sa.Enum(MembershipStatus, native_enum=False), nullable=False)


class _User:
    """Lightweight user exposing only what RBAC reads: ``id`` and ``roles``."""

    def __init__(self, user_id: str, roles: list[str]) -> None:
        self.id = user_id
        self.roles = roles


# Platform-role string values plus legacy/unknown strings that must be ignored
# by resolution (RBAC silently drops role strings that aren't a PlatformRole).
_PLATFORM_ROLE_VALUES = [role.value for role in PlatformRole]
_JUNK_ROLES = ["admin", "totally-unknown-role"]
_REQUIRED_PERMISSIONS = sorted(PERMISSION_CATALOG) + ["nonexistent:permission"]

# A (role, status) pair for a membership, or None for "no membership".
_membership_strategy = st.one_of(
    st.none(),
    st.tuples(st.sampled_from(list(TenantRole)), st.sampled_from(list(MembershipStatus))),
)


@pytest.fixture(autouse=True)
def _patch_membership(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point RBAC's Membership query at the SQLite-friendly test model."""
    monkeypatch.setattr(rbac, "Membership", _Membership)


def _expected_effective_permissions(
    platform_roles: list[str],
    target_membership: tuple[TenantRole, MembershipStatus] | None,
) -> frozenset[str]:
    """Independent oracle: union of recognized platform-role permissions and the
    permissions of an *active* membership in the target company."""
    expected: set[str] = set()
    for role_value in platform_roles:
        try:
            platform_role = PlatformRole(role_value)
        except ValueError:
            continue
        expected |= PLATFORM_ROLE_PERMISSIONS[platform_role]
    if target_membership is not None and target_membership[1] == MembershipStatus.active:
        expected |= TENANT_ROLE_PERMISSIONS[target_membership[0]]
    return frozenset(expected)


# Feature: multi-tenant-hiring-platform, Property 1: Authorization holds iff the required permission is present
# Validates: Requirements 4.5, 5.8, 17.1, 17.6
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    platform_roles=st.lists(
        st.sampled_from(_PLATFORM_ROLE_VALUES + _JUNK_ROLES),
        max_size=4,
        unique=True,
    ),
    target_membership=_membership_strategy,
    other_membership=_membership_strategy,
    required_permission=st.sampled_from(_REQUIRED_PERMISSIONS),
)
def test_authorization_holds_iff_permission_present(
    platform_roles: list[str],
    target_membership: tuple[TenantRole, MembershipStatus] | None,
    other_membership: tuple[TenantRole, MembershipStatus] | None,
    required_permission: str,
) -> None:
    """``has_permission`` is True iff the permission is in the effective set.

    The effective set is the union of the user's platform-role permissions and
    the permissions of the user's *active* membership in the company that owns
    the resource. Invited/suspended memberships contribute nothing, and
    memberships in other companies never leak into the target company's scope.
    """
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    _Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        user_id = str(uuid4())
        company_id = str(uuid4())
        other_company_id = str(uuid4())
        user = _User(user_id, list(platform_roles))

        if target_membership is not None:
            role, status = target_membership
            session.add(_Membership(user_id=user_id, company_id=company_id, role=role, status=status))
        if other_membership is not None:
            role, status = other_membership
            session.add(_Membership(user_id=user_id, company_id=other_company_id, role=role, status=status))
        session.commit()

        expected = _expected_effective_permissions(platform_roles, target_membership)

        # The full effective set must match the oracle exactly: this proves the
        # iff for every catalog permission in one shot.
        assert effective_permissions(session, user, company_id) == expected

        # And the generated required permission authorizes iff it is a member.
        assert has_permission(session, user, required_permission, company_id) == (required_permission in expected)
    finally:
        session.close()
        engine.dispose()
