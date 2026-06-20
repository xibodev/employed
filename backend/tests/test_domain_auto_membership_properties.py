"""Property-based test for idempotent domain auto-membership.

``app.services.memberships.apply_domain_auto_membership`` links a user to a
company whose verified email domain matches their address (R3.2). It is anchored
on the ``UniqueConstraint(user_id, company_id)`` invariant: when no membership
exists it creates one with status ``invited`` (R3.3) and records the action in
the audit trail (R3.5); when one already exists it updates that row in place
rather than inserting a duplicate (R3.4), preserving the existing status. The
policy is therefore idempotent — applying it any number of times leaves exactly
one membership for the pair (Property 15).

The production ``Membership`` model uses Postgres-only column types (native
``UUID``/``Enum``), so — as the company-creation and RBAC property tests do —
this test backs the service with a small SQLite-friendly stand-in model that
exposes exactly the columns the service touches, and points
``memberships.Membership`` at it. The real service code (the existing-row
lookup, the invited-on-create branch, the preserve-existing-status branch) runs
for real against an in-memory database.

``write_audit`` persists a Postgres-only ``AuditLog`` row, which has no table in
the SQLite stand-in schema, so it is monkeypatched to a no-op recorder. The
audit emission itself is covered by Property 9; here we only need the membership
side effects to run.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
import sqlalchemy as sa
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import TypeDecorator

from app.models.enums import MembershipStatus, TenantRole
from app.services import memberships
from app.services.memberships import apply_domain_auto_membership


class _Base(DeclarativeBase):
    pass


class _GUID(TypeDecorator):
    """Store UUIDs (or strings) as text so they bind cleanly on SQLite."""

    impl = sa.String(36)
    cache_ok = True

    def process_bind_param(self, value, _dialect):  # noqa: ANN001
        return None if value is None else str(value)

    def process_result_value(self, value, _dialect):  # noqa: ANN001
        return value


class _Membership(_Base):
    """SQLite-friendly stand-in for ``app.models.membership.Membership``.

    Only the columns ``apply_domain_auto_membership`` reads or writes are
    modelled; ``role``/``status`` use non-native ``Enum`` so reads return real
    enum members and the unique constraint mirrors production (R3.4).
    """

    __tablename__ = "memberships"
    __table_args__ = (sa.UniqueConstraint("user_id", "company_id", name="uq_memberships_user_company"),)

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(_GUID, index=True, nullable=False)
    company_id: Mapped[str] = mapped_column(_GUID, index=True, nullable=False)
    role: Mapped[TenantRole] = mapped_column(sa.Enum(TenantRole, native_enum=False), nullable=False)
    status: Mapped[MembershipStatus] = mapped_column(sa.Enum(MembershipStatus, native_enum=False), nullable=False)
    invited_by: Mapped[str | None] = mapped_column(_GUID)


def _make_session() -> tuple[Session, sa.Engine]:
    """Build a fresh in-memory SQLite session with the stand-in schema."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    _Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    return session, engine


@pytest.fixture(autouse=True)
def _patch_service(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the membership service at the stand-in model and neutralise audit.

    ``write_audit`` writes a Postgres-only ``AuditLog`` row with no SQLite table;
    a no-op recorder lets the create branch run without persisting an audit row.
    """
    monkeypatch.setattr(memberships, "Membership", _Membership)
    monkeypatch.setattr(memberships, "write_audit", lambda *args, **kwargs: None)


def _memberships_for(session: Session, *, user_id, company_id) -> list[_Membership]:
    return (
        session.execute(
            sa.select(_Membership).where(
                _Membership.user_id == str(user_id),
                _Membership.company_id == str(company_id),
            )
        )
        .scalars()
        .all()
    )


# Feature: multi-tenant-hiring-platform, Property 15: Domain auto-membership is idempotent
# Validates: Requirements 3.2, 3.3, 3.4
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    applications=st.integers(min_value=1, max_value=5),
    preexisting_status=st.sampled_from([None, *list(MembershipStatus)]),
    preexisting_role=st.sampled_from(list(TenantRole)),
)
def test_domain_auto_membership_is_idempotent(
    applications: int,
    preexisting_status: MembershipStatus | None,
    preexisting_role: TenantRole,
) -> None:
    """Applying the domain auto-membership policy one or more times yields
    exactly one membership for the user/company pair (R3.4); a newly created
    auto-membership has status ``invited`` (R3.3); an existing membership's
    deliberate status is preserved across repeated application.
    """
    session, engine = _make_session()
    try:
        user = SimpleNamespace(id=uuid4())
        company = SimpleNamespace(id=uuid4())

        if preexisting_status is not None:
            # A deliberate human decision already recorded on the membership.
            session.add(
                _Membership(
                    user_id=str(user.id),
                    company_id=str(company.id),
                    role=preexisting_role,
                    status=preexisting_status,
                )
            )
            session.flush()

        for _ in range(applications):
            apply_domain_auto_membership(session, company=company, user=user)
        session.commit()

        rows = _memberships_for(session, user_id=user.id, company_id=company.id)

        # R3.4: exactly one membership for the pair, never a duplicate, no matter
        # how many times the policy is applied.
        assert len(rows) == 1
        membership = rows[0]
        assert str(membership.user_id) == str(user.id)
        assert str(membership.company_id) == str(company.id)

        if preexisting_status is None:
            # R3.3: a newly created auto-membership starts as ``invited``.
            assert membership.status == MembershipStatus.invited
        else:
            # An existing membership's status is preserved (no demotion of an
            # active member, no silent reinstatement of a suspended one).
            assert membership.status == preexisting_status
    finally:
        session.close()
        engine.dispose()
