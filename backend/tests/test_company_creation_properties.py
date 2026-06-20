"""Property-based test for atomic company creation + owner membership.

``app.services.companies.create_company`` writes a ``Company`` row and the
creating user's ``org_owner``/``active`` ``Membership`` together in a single
unit of work (R1.4, R2.4). The membership insert runs inside a ``SAVEPOINT``
(``Session.begin_nested``) so a membership failure rolls the company back with
it (R2.5).

The production ``Company``/``Membership`` models use Postgres-only column types
(``JSONB``, native ``UUID``), so — as the RBAC property tests do — this test
backs ``create_company`` with small SQLite-friendly stand-in models that expose
exactly the columns the service touches, and points
``companies.Company`` / ``companies.Membership`` at them. The real service code
(slug generation, the nested-transaction owner-membership insert) therefore runs
for real against an in-memory database, genuinely exercising the atomic path.

``SAVEPOINT`` support on pysqlite requires disabling the driver's implicit
``BEGIN`` and emitting transaction control ourselves; the engine event hooks
below apply that well-known recipe so ``begin_nested()`` works on SQLite.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
import sqlalchemy as sa
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import TypeDecorator

from app.models.enums import MarketKey, MembershipStatus, TenantRole, VerificationState
from app.services import companies
from app.services.companies import create_company


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


class _Company(_Base):
    """SQLite-friendly stand-in for ``app.models.company.Company``.

    Only the columns ``create_company`` reads or writes are modelled. ``market``
    and ``verification_status`` use non-native ``Enum`` so reads return real enum
    members and the ``market``-scoped slug-uniqueness query binds correctly.
    JSONB list/dict columns become plain ``JSON`` with Python-side defaults.
    """

    __tablename__ = "companies"
    __table_args__ = (sa.UniqueConstraint("market", "slug", name="uq_companies_market_slug"),)

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    slug: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    market: Mapped[MarketKey] = mapped_column(sa.Enum(MarketKey, native_enum=False), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text)
    logo_url: Mapped[str | None] = mapped_column(sa.String(2048))
    website: Mapped[str | None] = mapped_column(sa.String(2048))
    verification_status: Mapped[VerificationState] = mapped_column(
        sa.Enum(VerificationState, native_enum=False), nullable=False
    )
    created_by: Mapped[str | None] = mapped_column(_GUID)
    verified_email_domains: Mapped[list] = mapped_column(sa.JSON, nullable=False, default=list)
    trust_badges: Mapped[list] = mapped_column(sa.JSON, nullable=False, default=list)
    external_refs: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)


class _Membership(_Base):
    """SQLite-friendly stand-in for ``app.models.membership.Membership``."""

    __tablename__ = "memberships"
    __table_args__ = (sa.UniqueConstraint("user_id", "company_id", name="uq_memberships_user_company"),)

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(_GUID, index=True, nullable=False)
    company_id: Mapped[str] = mapped_column(_GUID, index=True, nullable=False)
    role: Mapped[TenantRole] = mapped_column(sa.Enum(TenantRole, native_enum=False), nullable=False)
    status: Mapped[MembershipStatus] = mapped_column(sa.Enum(MembershipStatus, native_enum=False), nullable=False)
    invited_by: Mapped[str | None] = mapped_column(_GUID)


def _make_session() -> tuple[Session, sa.Engine]:
    """Build a fresh in-memory SQLite session with SAVEPOINT support enabled."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    # Enable SAVEPOINT (nested transactions) on pysqlite: turn off the driver's
    # implicit BEGIN and emit transaction control ourselves so begin_nested()
    # issues real SAVEPOINT/RELEASE statements.
    @event.listens_for(engine, "connect")
    def _sqlite_no_implicit_begin(dbapi_connection, _record):  # noqa: ANN001
        dbapi_connection.isolation_level = None

    @event.listens_for(engine, "begin")
    def _sqlite_emit_begin(conn):  # noqa: ANN001
        conn.exec_driver_sql("BEGIN")

    _Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    return session, engine


@pytest.fixture(autouse=True)
def _patch_models(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the company service at the SQLite-friendly stand-in models."""
    monkeypatch.setattr(companies, "Company", _Company)
    monkeypatch.setattr(companies, "Membership", _Membership)


# Feature: multi-tenant-hiring-platform, Property 4: Creating a company yields an active org_owner membership
# Validates: Requirements 1.4, 2.4
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    name=st.text(min_size=1, max_size=80),
    market=st.sampled_from(list(MarketKey)),
)
def test_creating_company_yields_active_org_owner_membership(name: str, market: MarketKey) -> None:
    """After ``create_company`` there is exactly one ``org_owner``/``active``
    membership linking the creating user to the new company, and the company's
    ``created_by`` equals that user.
    """
    session, engine = _make_session()
    try:
        creator_id = uuid4()

        company = create_company(session, name=name, market=market, created_by=creator_id)
        session.commit()

        # The company records its creator (R1.4) and starts unverified.
        assert company.created_by == creator_id
        assert company.verification_status == VerificationState.unverified
        assert company.market == market

        # Exactly one membership exists for this company, and it links the
        # creating user as an active org_owner (R2.4).
        memberships = (
            session.execute(sa.select(_Membership).where(_Membership.company_id == company.id)).scalars().all()
        )
        assert len(memberships) == 1
        owner = memberships[0]
        assert str(owner.user_id) == str(creator_id)
        assert owner.company_id == company.id
        assert owner.role == TenantRole.org_owner
        assert owner.status == MembershipStatus.active

        # No other membership links this user to any other company in this DB.
        all_for_user = (
            session.execute(sa.select(_Membership).where(_Membership.user_id == str(creator_id))).scalars().all()
        )
        assert len(all_for_user) == 1
    finally:
        session.close()
        engine.dispose()
