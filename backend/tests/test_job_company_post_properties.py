"""Property-based test for posting a job on behalf of a company (R4.4).

Exercises the router authorization helper ``jobs._authorize_company_post``,
which is what resolves the ``company_id`` that ``create_job`` then stamps onto
the new job. The helper delegates to ``rbac.has_permission(db, user, JOB_POST,
company_id=...)``, so the test backs that query with a small in-memory SQLite
``Membership`` model and points ``rbac.Membership`` at it. The real
``status == active`` WHERE-clause filtering therefore executes for real, rather
than being re-modelled by a hand-rolled fake.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.enums import MembershipStatus, TenantRole
from app.routers import jobs
from app.services import rbac
from app.services.rbac import JOB_POST, TENANT_ROLE_PERMISSIONS


class _Base(DeclarativeBase):
    pass


class _Membership(_Base):
    """SQLite-friendly stand-in for ``app.models.membership.Membership``.

    Only the columns RBAC resolution reads are modelled. ``role`` / ``status``
    use SQLAlchemy ``Enum`` so reads return real enum members (matching the
    production model) and the ``status == active`` filter binds correctly.
    """

    __tablename__ = "memberships"

    # ``user_id`` / ``company_id`` are UUID-typed to mirror the production
    # ``PGUUID`` columns: ``_authorize_company_post`` coerces the payload's
    # company id to a ``UUID`` before querying, so the column must compare
    # equal to a ``UUID`` bind value.
    id: Mapped[UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(sa.Uuid, index=True)
    company_id: Mapped[UUID] = mapped_column(sa.Uuid, index=True)
    role: Mapped[TenantRole] = mapped_column(sa.Enum(TenantRole, native_enum=False), nullable=False)
    status: Mapped[MembershipStatus] = mapped_column(sa.Enum(MembershipStatus, native_enum=False), nullable=False)


class _User:
    """Lightweight user exposing only what RBAC reads: ``id`` and ``roles``.

    No platform roles, so authorization can only come from the tenant
    membership — isolating the on-behalf-of company path.
    """

    def __init__(self, user_id: UUID) -> None:
        self.id = user_id
        self.roles: list[str] = []


class _Payload:
    """Minimal JobCreate-like payload: the helper only reads ``company_id``."""

    def __init__(self, company_id: str | None) -> None:
        self.company_id = company_id


@pytest.fixture(autouse=True)
def _patch_membership(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point RBAC's Membership query at the SQLite-friendly test model."""
    monkeypatch.setattr(rbac, "Membership", _Membership)


def _new_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    _Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    return engine, session


# Feature: multi-tenant-hiring-platform, Property 16: Posting on behalf of a company sets company_id
# Validates: Requirements 4.4
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    role=st.sampled_from(list(TenantRole)),
    status=st.sampled_from(list(MembershipStatus)),
)
def test_posting_on_behalf_of_company_sets_company_id(
    role: TenantRole,
    status: MembershipStatus,
) -> None:
    """``_authorize_company_post`` returns the company id iff the caller holds
    ``job:post`` there via an active membership; otherwise it rejects with 403.

    The returned id is what ``create_job`` stamps onto ``job.company_id`` (R4.4),
    so resolving the company id is equivalent to the job being attributed to it.
    """
    engine, session = _new_session()
    try:
        user_id = uuid4()
        company_id = uuid4()
        user = _User(user_id)
        session.add(_Membership(user_id=user_id, company_id=company_id, role=role, status=status))
        session.commit()

        # Payload carries the company id as a string (as it arrives over JSON);
        # the helper coerces it to a UUID.
        payload = _Payload(company_id=str(company_id))

        grants_job_post = status == MembershipStatus.active and JOB_POST in TENANT_ROLE_PERMISSIONS[role]

        if grants_job_post:
            resolved = jobs._authorize_company_post(session, payload, user)
            # The job's company_id will be set to exactly this company (R4.4).
            assert resolved == company_id
        else:
            # No job:post in the company -> rejected with 403 (R4.5).
            with pytest.raises(HTTPException) as exc_info:
                jobs._authorize_company_post(session, payload, user)
            assert exc_info.value.status_code == 403
    finally:
        session.close()
        engine.dispose()


# Feature: multi-tenant-hiring-platform, Property 16: Posting on behalf of a company sets company_id
# Validates: Requirements 4.4
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(role=st.sampled_from(list(TenantRole)), status=st.sampled_from(list(MembershipStatus)))
def test_anonymous_post_without_company_id_resolves_to_none(
    role: TenantRole,
    status: MembershipStatus,
) -> None:
    """When no ``company_id`` is supplied the post is a legacy/anonymous listing
    (R4.3): the helper returns ``None`` regardless of any membership the caller
    happens to hold, so no company attribution is stamped onto the job."""
    engine, session = _new_session()
    try:
        user_id = uuid4()
        user = _User(user_id)
        # An unrelated membership must not cause a company to be inferred.
        session.add(_Membership(user_id=user_id, company_id=uuid4(), role=role, status=status))
        session.commit()

        assert jobs._authorize_company_post(session, _Payload(company_id=None), user) is None
    finally:
        session.close()
        engine.dispose()
