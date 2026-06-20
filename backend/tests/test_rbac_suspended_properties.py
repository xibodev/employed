"""Property-based tests for suspended-membership authorization (RBAC).

# Feature: multi-tenant-hiring-platform, Property 3: Suspended memberships grant no tenant permissions

A suspended membership must contribute no tenant-scoped permissions, regardless
of the tenant role it carries. The enforcement lives in
``rbac._tenant_permissions`` / ``rbac.effective_permissions``, whose query only
counts ``active`` memberships (``invited``/``suspended`` grant none).

These tests exercise the real resolution path against an in-memory SQLite
session holding a real :class:`Membership` row, so the active-only query filter
itself is under test (not mocked away).

**Validates: Requirements 2.10**
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models.enums import MembershipStatus, TenantRole
from app.models.membership import Membership
from app.services import rbac


def _make_session() -> Session:
    """A fresh in-memory SQLite session with only the memberships table.

    The real model's ``id`` server default (``gen_random_uuid()``) is
    Postgres-only, so every row is created with an explicit UUID id.
    """

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Membership.__table__.create(engine)
    return sessionmaker(bind=engine, future=True)()


@settings(max_examples=100, deadline=None)
@given(
    role=st.sampled_from(list(TenantRole)),
    user_id=st.uuids(),
    company_id=st.uuids(),
    invited_by=st.one_of(st.none(), st.uuids()),
)
def test_suspended_membership_grants_no_tenant_permissions(
    role: TenantRole,
    user_id: UUID,
    company_id: UUID,
    invited_by: UUID | None,
) -> None:
    """For any role, a suspended membership contributes an empty permission set."""

    db = _make_session()
    try:
        db.add(
            Membership(
                id=uuid4(),
                user_id=user_id,
                company_id=company_id,
                role=role,
                status=MembershipStatus.suspended,
                invited_by=invited_by,
            )
        )
        db.commit()

        # A user carrying no platform roles, so effective == tenant permissions.
        user = SimpleNamespace(id=user_id, roles=[])

        # The suspended membership contributes nothing...
        assert rbac._tenant_permissions(db, user, company_id) == frozenset()
        # ...and with no platform roles the effective set is therefore empty.
        assert rbac.effective_permissions(db, user, company_id) == frozenset()

        # Guard against a vacuous pass: the same role, while ACTIVE, would have
        # carried its full permission bundle. Suspension is what suppresses it.
        same = db.query(Membership).filter(Membership.user_id == user_id).first()
        assert same is not None
        same.status = MembershipStatus.active
        db.commit()
        assert rbac._tenant_permissions(db, user, company_id) == rbac.TENANT_ROLE_PERMISSIONS[role]
    finally:
        db.close()
