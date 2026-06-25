from __future__ import annotations

import builtins
import json
import re
import sys
import types
from collections.abc import Callable, Generator
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Boolean, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import TypeDecorator

builtins.UUID = UUID

if "slugify" not in sys.modules:
    slugify_module = types.ModuleType("slugify")

    def _slugify(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-") or "job"

    slugify_module.slugify = _slugify
    sys.modules["slugify"] = slugify_module

if "bleach" not in sys.modules:
    bleach_module = types.ModuleType("bleach")
    bleach_module.clean = lambda value, **kwargs: value or ""
    bleach_module.linkify = lambda value, callbacks=None: value or ""
    sys.modules["bleach"] = bleach_module

import app.models as app_models
from app.auth.jwt import create_access_token
from app.main import create_app
from app.middleware.rate_limit import close_quietly, rate_limiter, redis_client
from app.routers.auth import failed_login_tracker
from app.services.market import MARKETS
from app.webhooks import mobile_money, stripe_webhook


class TestBase(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json_sanitize(value: Any) -> Any:
    if isinstance(value, datetime):
        aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return aware.astimezone(timezone.utc).isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, list):
        return [_json_sanitize(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_sanitize(item) for key, item in value.items()}
    return value


class JSONEncoded(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect) -> str | None:
        if value is None:
            return None
        return json.dumps(_json_sanitize(value))

    def process_result_value(self, value: str | None, dialect) -> Any:
        return json.loads(value) if value is not None else None


class AwareDateTime(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> str | None:
        if value is None:
            return None
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()

    def process_result_value(self, value: str | None, dialect) -> datetime | None:
        if value is None:
            return None
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class User(TestBase):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str | None] = mapped_column(String(320), unique=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    username: Mapped[str | None] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(128))
    roles: Mapped[list[str]] = mapped_column(JSONEncoded(), default=list)
    oauth_providers: Mapped[dict[str, Any]] = mapped_column(JSONEncoded(), default=dict)
    deletion_requested_at: Mapped[datetime | None] = mapped_column(AwareDateTime())
    deletion_scheduled_for: Mapped[datetime | None] = mapped_column(AwareDateTime())
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow, onupdate=utcnow)


class Job(TestBase):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str | None] = mapped_column(String(36), index=True)
    title: Mapped[str] = mapped_column(String(256))
    slug: Mapped[str | None] = mapped_column(String(256))
    company: Mapped[str | None] = mapped_column(String(256))
    country: Mapped[str] = mapped_column(String(32))
    location: Mapped[str | None] = mapped_column(String(256))
    url: Mapped[str | None] = mapped_column(String(2048))
    contact: Mapped[str] = mapped_column(String(512))
    apply_whatsapp: Mapped[str | None] = mapped_column(String(32))
    job_type: Mapped[str] = mapped_column(String(32))
    remote: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str] = mapped_column(Text)
    html_description: Mapped[str | None] = mapped_column(Text)
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str | None] = mapped_column(String(8))
    salary_period: Mapped[str | None] = mapped_column(String(16))
    user_name: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    featured_through: Mapped[datetime | None] = mapped_column(AwareDateTime())
    featured_charge_history: Mapped[list[dict[str, Any]]] = mapped_column(JSONEncoded(), default=list)
    status_history: Mapped[list[dict[str, Any]]] = mapped_column(JSONEncoded(), default=list)
    published_at: Mapped[datetime | None] = mapped_column(AwareDateTime())
    expired_at: Mapped[datetime | None] = mapped_column(AwareDateTime())
    recaptcha_score: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow, onupdate=utcnow)


class Profile(TestBase):
    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    user_name: Mapped[str | None] = mapped_column(String(128))
    custom_image_url: Mapped[str | None] = mapped_column(String(2048))
    name: Mapped[str] = mapped_column(String(128))
    type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(128))
    location: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text)
    html_description: Mapped[str | None] = mapped_column(Text)
    available_for_hire: Mapped[bool] = mapped_column(Boolean, default=False)
    interested_in: Mapped[list[str]] = mapped_column(JSONEncoded(), default=list)
    contact: Mapped[str | None] = mapped_column(String(512))
    url: Mapped[str | None] = mapped_column(String(2048))
    resume_url: Mapped[str | None] = mapped_column(String(2048))
    github_url: Mapped[str | None] = mapped_column(String(2048))
    linkedin_url: Mapped[str | None] = mapped_column(String(2048))
    stackoverflow_url: Mapped[str | None] = mapped_column(String(2048))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    random_sorter: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow, onupdate=utcnow)


class PaymentIntent(TestBase):
    __tablename__ = "payment_intents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    job_id: Mapped[str] = mapped_column(String(36), index=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    market_key: Mapped[str] = mapped_column(String(8))
    provider_key: Mapped[str] = mapped_column(String(16))
    provider_ref: Mapped[str | None] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(8))
    payer_msisdn: Mapped[str | None] = mapped_column(String(64))
    payer_msisdn_hash: Mapped[str | None] = mapped_column(String(64))
    extended_through: Mapped[datetime | None] = mapped_column(AwareDateTime())
    failure_reason: Mapped[str | None] = mapped_column(String(256))
    simulator: Mapped[bool] = mapped_column(Boolean, default=False)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONEncoded(), default=dict)
    settled_at: Mapped[datetime | None] = mapped_column(AwareDateTime())
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow, onupdate=utcnow)


class JobReport(TestBase):
    __tablename__ = "job_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    job_id: Mapped[str] = mapped_column(String(36), index=True)
    reason: Mapped[str] = mapped_column(String(32))
    details: Mapped[str | None] = mapped_column(String(2000))
    reporter_ip_hash: Mapped[str | None] = mapped_column(String(64))
    reporter_user_id: Mapped[str | None] = mapped_column(String(36), index=True)
    resolution: Mapped[str] = mapped_column(String(32), default="pending")
    resolved_by: Mapped[str | None] = mapped_column(String(36))
    resolved_at: Mapped[datetime | None] = mapped_column(AwareDateTime())
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utcnow, onupdate=utcnow)


TEST_MODELS = {
    "User": User,
    "Job": Job,
    "Profile": Profile,
    "PaymentIntent": PaymentIntent,
    "JobReport": JobReport,
}


def _flush_test_redis() -> None:
    """Flush the Redis DB used by the test environment, if one is configured.

    Rate-limit, lockout, JTI-revocation and webhook-replay state live in Redis
    whenever REDIS_URL is set (e.g. CI). Flushing between tests keeps each test
    isolated. Best-effort: a missing or unreachable Redis is a no-op (the
    in-process fallbacks are already cleared by the autouse fixture)."""
    client = redis_client()
    if client is None:
        return
    try:
        client.flushdb()
    except Exception:  # noqa: BLE001 — test isolation must never hard-fail on infra
        pass
    finally:
        close_quietly(client)


@pytest.fixture(autouse=True)
def _patch_models(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, model in TEST_MODELS.items():
        monkeypatch.setattr(app_models, name, model, raising=False)
    monkeypatch.setattr("app.payments.settlement.coerce_pk", lambda value: str(value) if value is not None else None)
    monkeypatch.setattr(
        "app.webhooks.stripe_webhook.coerce_pk", lambda value: str(value) if value is not None else None
    )
    monkeypatch.setattr("app.webhooks.mobile_money.coerce_pk", lambda value: str(value) if value is not None else None)
    # Reset the in-process rate-limit and lockout stores between tests.
    rate_limiter._buckets.clear()
    failed_login_tracker.clear()
    # When REDIS_URL is set (CI), rate-limit counters, lockout state, JTI
    # revocation and webhook replay keys live in Redis — not the in-process
    # stores above. Without flushing them, fixed-window counters accumulate
    # across tests and later requests get a spurious 429. Flush the test DB so
    # each test starts clean. No-op locally where Redis is absent.
    _flush_test_redis()


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    TestBase.metadata.create_all(engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        TestBase.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    from app.database import get_db

    app = create_app()
    existing_paths = {route.path for route in app.routes}
    if "/_stripe/webhook" not in existing_paths:
        app.include_router(stripe_webhook.router)
    if "/_mpesa/callback" not in existing_paths:
        app.include_router(mobile_money.router)

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def user_factory(db_session: Session) -> Callable[..., User]:
    from app.auth.passwords import hash_password

    def factory(
        *,
        email: str | None = None,
        password: str = "password123",
        verified: bool = True,
        roles: list[str] | None = None,
        display_name: str | None = None,
        oauth_providers: dict[str, Any] | None = None,
    ) -> User:
        user = User(
            email=email or f"user-{uuid4().hex[:8]}@example.com",
            email_verified=verified,
            password_hash=hash_password(password),
            display_name=display_name or "Test User",
            roles=list(roles or []),
            oauth_providers=oauth_providers or {},
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user

    return factory


@pytest.fixture()
def test_user(user_factory: Callable[..., User]) -> User:
    return user_factory(email="user@example.com", display_name="Regular User")


@pytest.fixture()
def test_admin(user_factory: Callable[..., User]) -> User:
    return user_factory(email="admin@example.com", roles=["admin"], display_name="Admin User")


@pytest.fixture()
def auth_headers() -> Callable[[User], dict[str, str]]:
    def factory(user: User) -> dict[str, str]:
        token = create_access_token(str(user.id))
        return {"Authorization": f"Bearer {token}"}

    return factory


@pytest.fixture()
def sample_market_headers() -> Callable[[str], dict[str, str]]:
    def factory(market_key: str) -> dict[str, str]:
        return {"Host": f"{market_key}.employed.co.mz"}

    return factory


@pytest.fixture()
def job_factory(db_session: Session) -> Callable[..., Job]:
    def factory(
        *,
        user: User | None = None,
        status: str = "active",
        country: str = MARKETS["mz"]["country"],
        title: str = "Backend Engineer",
        company: str = "Acme",
        remote: bool = False,
        featured: bool = False,
        created_at: datetime | None = None,
        published_at: datetime | None = None,
        job_type: str = "Full Time",
    ) -> Job:
        now = utcnow()
        job = Job(
            user_id=user.id if user else None,
            user_name=user.display_name if user else None,
            title=title,
            slug=title.lower().replace(" ", "-"),
            company=company,
            country=country,
            location="Maputo",
            url="https://example.com/jobs/backend-engineer",
            contact="jobs@example.com",
            apply_whatsapp="258840000000",
            job_type=job_type,
            remote=remote,
            description="Build great products",
            html_description="<p>Build great products</p>",
            status=status,
            featured_through=(now + timedelta(days=30)) if featured else None,
            featured_charge_history=[],
            status_history=[],
            created_at=created_at or now,
            updated_at=now,
            published_at=published_at or now,
        )
        db_session.add(job)
        db_session.commit()
        db_session.refresh(job)
        return job

    return factory


@pytest.fixture()
def sample_job(job_factory: Callable[..., Job], test_user: User) -> Callable[..., Job]:
    def factory(user: User | None = None, **kwargs: Any) -> Job:
        return job_factory(user=user or test_user, **kwargs)

    return factory


@pytest.fixture()
def profile_factory(db_session: Session) -> Callable[..., Profile]:
    def factory(*, user: User, status: str = "active", **kwargs: Any) -> Profile:
        profile = Profile(
            user_id=user.id,
            user_name=user.display_name,
            name=kwargs.get("name", "Regular User"),
            type=kwargs.get("type", "Individual"),
            title=kwargs.get("title", "Engineer"),
            location=kwargs.get("location", "Maputo"),
            description=kwargs.get("description", "About me"),
            html_description=kwargs.get("html_description", "<p>About me</p>"),
            available_for_hire=kwargs.get("available_for_hire", True),
            interested_in=kwargs.get("interested_in", ["Full Time"]),
            contact=kwargs.get("contact", "profile@example.com"),
            url=kwargs.get("url", "https://example.com"),
            resume_url=kwargs.get("resume_url", "https://example.com/resume.pdf"),
            github_url=kwargs.get("github_url", "https://github.com/example"),
            linkedin_url=kwargs.get("linkedin_url", "https://linkedin.com/in/example"),
            stackoverflow_url=kwargs.get("stackoverflow_url", "https://stackoverflow.com/users/1/example"),
            custom_image_url=kwargs.get("custom_image_url", "https://example.com/avatar.png"),
            status=status,
            created_at=kwargs.get("created_at", utcnow()),
            updated_at=kwargs.get("updated_at", utcnow()),
        )
        db_session.add(profile)
        db_session.commit()
        db_session.refresh(profile)
        return profile

    return factory


@pytest.fixture()
def payment_intent_factory(db_session: Session) -> Callable[..., PaymentIntent]:
    def factory(
        *,
        job: Job,
        user: User,
        provider_key: str = "stripe",
        status: str = "pending",
        market_key: str = "mz",
        **kwargs: Any,
    ) -> PaymentIntent:
        intent = PaymentIntent(
            job_id=job.id,
            user_id=user.id,
            market_key=market_key,
            provider_key=provider_key,
            provider_ref=kwargs.get("provider_ref"),
            status=status,
            amount=kwargs.get("amount", 250000),
            currency=kwargs.get("currency", "mzn"),
            payer_msisdn=kwargs.get("payer_msisdn"),
            payer_msisdn_hash=kwargs.get("payer_msisdn_hash"),
            extended_through=kwargs.get("extended_through", utcnow() + timedelta(days=30)),
            failure_reason=kwargs.get("failure_reason"),
            simulator=kwargs.get("simulator", provider_key != "stripe"),
            meta=kwargs.get("meta", {}),
            settled_at=kwargs.get("settled_at"),
            created_at=kwargs.get("created_at", utcnow()),
            updated_at=kwargs.get("updated_at", utcnow()),
        )
        db_session.add(intent)
        db_session.commit()
        db_session.refresh(intent)
        return intent

    return factory


@pytest.fixture()
def report_factory(db_session: Session) -> Callable[..., JobReport]:
    def factory(*, job: Job, reporter: User | None = None, resolution: str = "pending", **kwargs: Any) -> JobReport:
        report = JobReport(
            job_id=job.id,
            reason=kwargs.get("reason", "spam"),
            details=kwargs.get("details", "Looks suspicious"),
            reporter_ip_hash=kwargs.get("reporter_ip_hash", "abc123"),
            reporter_user_id=reporter.id if reporter else None,
            resolution=resolution,
            resolved_by=kwargs.get("resolved_by"),
            resolved_at=kwargs.get("resolved_at"),
            created_at=kwargs.get("created_at", utcnow()),
            updated_at=kwargs.get("updated_at", utcnow()),
        )
        db_session.add(report)
        db_session.commit()
        db_session.refresh(report)
        return report

    return factory
