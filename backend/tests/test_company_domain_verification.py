"""Integration test for DNS TXT Company domain verification (R9.1).

``app.services.companies.verify_domain_via_dns`` resolves the TXT records for a
claimed domain through an injectable ``resolver`` callable and, when the expected
verification token is published among them, attaches the domain to the company:
it appends the domain to ``verified_email_domains`` (R9.5) and reconciles trust
badges so the "domain verified" badge attaches (R9.3). A non-matching domain
returns ``False`` and changes nothing (R9.4 — the result is never spuriously
asserted).

The production ``Company`` model uses Postgres-only column types (``JSONB``), so
— as the company creation / slug property tests do — this test backs the service
with a small SQLite-friendly stand-in ``Company`` that exposes exactly the
columns the verification path touches (``verified_email_domains``,
``trust_badges``, ``external_refs``, ``verification_status``). The real service
code (token matching, the SAVEPOINT-guarded list append, badge reconciliation)
therefore runs for real against an in-memory database.

Two modules reference ``Company`` and both are pointed at the stand-in:
``app.services.companies`` (only relevant for completeness) and, crucially,
``app.services.trust`` — :func:`~app.services.trust.derive_badges` dispatches on
``isinstance(entity, Company)``, so the stand-in must be recognised as a Company
for the "domain verified" badge to derive.

``SAVEPOINT`` support on pysqlite requires disabling the driver's implicit
``BEGIN`` and emitting transaction control ourselves; the engine event hooks
below apply that well-known recipe so the service's ``begin_nested()`` works on
SQLite.
"""

from __future__ import annotations

from collections.abc import Iterable
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine, event
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.enums import MarketKey, VerificationState
from app.services import companies, trust
from app.services.companies import verify_domain_via_dns


class _Base(DeclarativeBase):
    pass


class _Company(_Base):
    """SQLite-friendly stand-in for ``app.models.company.Company``.

    Only the columns the domain-verification path reads or writes are modelled.
    The JSONB list/dict columns become plain ``JSON`` wrapped in the mutable
    extensions so in-place ``append``/mutation is change-tracked, matching the
    production model's ``MutableList``/``MutableDict`` semantics.
    """

    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    slug: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    market: Mapped[MarketKey] = mapped_column(sa.Enum(MarketKey, native_enum=False), nullable=False)
    verification_status: Mapped[VerificationState] = mapped_column(
        sa.Enum(VerificationState, native_enum=False), nullable=False
    )
    verified_email_domains: Mapped[list] = mapped_column(
        MutableList.as_mutable(sa.JSON), nullable=False, default=list
    )
    trust_badges: Mapped[list] = mapped_column(MutableList.as_mutable(sa.JSON), nullable=False, default=list)
    external_refs: Mapped[dict] = mapped_column(MutableDict.as_mutable(sa.JSON), nullable=False, default=dict)


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
    # issues real SAVEPOINT/RELEASE statements (the service attaches the domain
    # inside a SAVEPOINT).
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
    """Point the company service and trust module at the stand-in Company.

    Patching ``trust.Company`` is essential: ``derive_badges`` dispatches on
    ``isinstance(entity, Company)``, so the stand-in must be recognised as a
    Company for the "domain verified" badge to attach.
    """
    monkeypatch.setattr(companies, "Company", _Company)
    monkeypatch.setattr(trust, "Company", _Company)


def _make_company(session: Session) -> _Company:
    """Persist an unverified company with empty verification/badge state."""
    company = _Company(
        name="Acme Co",
        slug="acme-co",
        market=MarketKey.mz,
        verification_status=VerificationState.unverified,
        verified_email_domains=[],
        trust_badges=[],
        external_refs={},
    )
    session.add(company)
    session.flush()
    return company


def test_dns_txt_matching_token_verifies_domain_and_attaches_badge() -> None:
    """A TXT record carrying the expected token verifies the domain (R9.1).

    The function returns ``True``, the claimed domain is appended to
    ``verified_email_domains`` (R9.5), and the "domain verified" trust badge is
    attached via badge reconciliation (R9.3).
    """
    session, engine = _make_session()
    try:
        company = _make_company(session)
        token = "employed-verify=abc123token"

        seen: list[str] = []

        def resolver(domain: str) -> Iterable[str]:
            # Records the lookup so we can assert no real DNS is used and the
            # normalized domain is queried, then returns TXT records that include
            # the expected token (surrounded by other unrelated records).
            seen.append(domain)
            return ["v=spf1 include:_spf.example.com ~all", f"  {token}  "]

        result = verify_domain_via_dns(
            session,
            company=company,
            domain="Acme.com",
            expected_token=token,
            resolver=resolver,
        )

        assert result is True
        # The injected resolver was used (no real DNS) and queried the normalized
        # (lower-cased) domain.
        assert seen == ["acme.com"]
        # The domain was appended (R9.5), normalized to lower case.
        assert company.verified_email_domains == ["acme.com"]
        # The "domain verified" badge is now attached (R9.3); no other badge
        # condition holds for this company.
        assert "domain verified" in company.trust_badges
        assert company.trust_badges == ["domain verified"]
    finally:
        session.close()
        engine.dispose()


def test_dns_txt_missing_token_does_not_verify_or_mutate() -> None:
    """TXT records without the expected token do not verify the domain (R9.1/9.4).

    The function returns ``False`` and nothing changes: the domain is not
    appended and no badge is attached.
    """
    session, engine = _make_session()
    try:
        company = _make_company(session)

        def resolver(domain: str) -> Iterable[str]:
            # No record matches the expected token.
            return ["v=spf1 include:_spf.example.com ~all", "google-site-verification=other"]

        result = verify_domain_via_dns(
            session,
            company=company,
            domain="acme.com",
            expected_token="employed-verify=abc123token",
            resolver=resolver,
        )

        assert result is False
        # Nothing was mutated: no domain appended and no badge attached.
        assert company.verified_email_domains == []
        assert company.trust_badges == []
    finally:
        session.close()
        engine.dispose()


def test_dns_txt_verification_is_idempotent() -> None:
    """Re-verifying an already-verified domain does not duplicate it (R9.5).

    The append step is idempotent: a second successful verification of the same
    domain leaves a single entry and the single "domain verified" badge.
    """
    session, engine = _make_session()
    try:
        company = _make_company(session)
        token = "employed-verify=abc123token"

        def resolver(domain: str) -> Iterable[str]:
            return [token]

        first = verify_domain_via_dns(
            session, company=company, domain="acme.com", expected_token=token, resolver=resolver
        )
        second = verify_domain_via_dns(
            session, company=company, domain="acme.com", expected_token=token, resolver=resolver
        )

        assert first is True
        assert second is True
        assert company.verified_email_domains == ["acme.com"]
        assert company.trust_badges == ["domain verified"]
    finally:
        session.close()
        engine.dispose()
