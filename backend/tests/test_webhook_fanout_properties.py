"""Property-based test for webhook event fan-out (Property 18).

:func:`app.services.webhooks.emit` must fan a domain event out to *exactly* the
active endpoints subscribed to that event: it persists one ``pending``
``WebhookDelivery`` per subscribed endpoint and none for endpoints that are
inactive or not subscribed (R20.1/20.2/20.3/20.4; the same fan-out backs the
job.published / application.created emissions of R16.6 / R17.4).

The production ``WebhookEndpoint`` / ``WebhookDelivery`` models use Postgres-only
column types (``JSONB`` and a native enum), so they cannot be materialised on the
in-memory SQLite engine. Following the convention of
``test_single_live_profile_properties.py``, this test defines SQLite-friendly
stand-in models carrying exactly the columns ``emit`` reads and writes, and
points the service module at them via monkeypatch. The real ``_subscribed_endpoints``
query and delivery-persistence code paths therefore execute for real against an
in-memory database. ``_enqueue_delivery`` is patched to a no-op so the test never
reaches for Redis/arq.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
import sqlalchemy as sa
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import create_engine
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.enums import WebhookEvent
from app.services import webhooks


class _Base(DeclarativeBase):
    pass


class _WebhookEndpoint(_Base):
    """SQLite-friendly stand-in for ``app.models.webhook.WebhookEndpoint``.

    Only the columns the fan-out query reads are modelled: ``events`` (the set
    of subscribed ``WebhookEvent`` values, stored as JSON) and ``active`` (the
    ``WHERE active`` predicate). ``id`` carries a Python-side default so freshly
    added endpoints get an id without the production ``gen_random_uuid()``
    server default.
    """

    __tablename__ = "webhook_endpoints"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=lambda: str(uuid4()))
    company_id: Mapped[str | None] = mapped_column(sa.String(36))
    url: Mapped[str] = mapped_column(sa.String(2048), nullable=False)
    secret: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    events: Mapped[list[str]] = mapped_column(MutableList.as_mutable(sa.JSON), nullable=False, default=list)
    active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)


class _WebhookDelivery(_Base):
    """SQLite-friendly stand-in for ``app.models.webhook.WebhookDelivery``.

    The native-enum ``event`` column is modelled with a non-native ``Enum`` so
    SQLite can round-trip the ``WebhookEvent`` member ``emit`` assigns.
    """

    __tablename__ = "webhook_deliveries"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=lambda: str(uuid4()))
    endpoint_id: Mapped[str] = mapped_column(sa.String(36), nullable=False, index=True)
    event: Mapped[WebhookEvent] = mapped_column(sa.Enum(WebhookEvent, native_enum=False), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(sa.JSON), nullable=False, default=dict)
    status: Mapped[str] = mapped_column(sa.String(32), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)


@pytest.fixture(autouse=True)
def _patch_webhook_models(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the service at the SQLite stand-ins and stub out enqueue.

    ``emit`` calls ``_enqueue_delivery`` (which would create an arq pool over
    Redis) once per persisted delivery; patching it to a no-op keeps the test
    purely about the persisted fan-out without any external dependency.
    """
    monkeypatch.setattr(webhooks, "WebhookEndpoint", _WebhookEndpoint)
    monkeypatch.setattr(webhooks, "WebhookDelivery", _WebhookDelivery)
    monkeypatch.setattr(webhooks, "_enqueue_delivery", lambda delivery_id: None)


def _build_session() -> tuple[Session, sa.Engine]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    _Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    return session_factory(), engine


_ALL_EVENTS = list(WebhookEvent)


@st.composite
def _endpoint_specs(draw: st.DrawFn) -> list[dict[str, Any]]:
    """A list of endpoint specs, each with an arbitrary event-subscription
    subset and an active flag, so fan-out sees every combination of
    subscribed/unsubscribed and active/inactive."""
    return draw(
        st.lists(
            st.fixed_dictionaries(
                {
                    "events": st.lists(st.sampled_from(_ALL_EVENTS), unique=True, max_size=len(_ALL_EVENTS)),
                    "active": st.booleans(),
                    "platform": st.booleans(),
                }
            ),
            max_size=8,
        )
    )


# Feature: multi-tenant-hiring-platform, Property 18: Event emission fans out to subscribed endpoints only
@settings(max_examples=100, deadline=None)
@given(specs=_endpoint_specs(), event=st.sampled_from(_ALL_EVENTS))
def test_emit_fans_out_to_subscribed_active_endpoints_only(specs: list[dict[str, Any]], event: WebhookEvent) -> None:
    """For any set of registered endpoints, ``emit`` persists exactly one pending
    ``WebhookDelivery`` per ACTIVE endpoint subscribed to the event and none for
    endpoints that are inactive or not subscribed.

    Validates: Requirements 16.6, 17.4, 20.1, 20.2, 20.3, 20.4
    """
    db, engine = _build_session()
    try:
        expected_endpoint_ids: set[str] = set()
        for spec in specs:
            endpoint = _WebhookEndpoint(
                company_id=(str(uuid4()) if spec["platform"] else None),
                url="https://example.test/hook",
                secret="shh",
                events=[e.value for e in spec["events"]],
                active=spec["active"],
            )
            db.add(endpoint)
            db.flush()
            if spec["active"] and event in spec["events"]:
                expected_endpoint_ids.add(endpoint.id)

        payload = {"id": "entity-1", "event": event.value}
        deliveries = webhooks.emit(db, event, payload)

        # The returned deliveries and the persisted rows must agree, and target
        # exactly the active+subscribed endpoints -- no more, no fewer.
        persisted = db.query(_WebhookDelivery).all()
        assert {d.endpoint_id for d in persisted} == expected_endpoint_ids
        assert {d.endpoint_id for d in deliveries} == expected_endpoint_ids
        assert len(persisted) == len(deliveries) == len(expected_endpoint_ids)

        # Every persisted delivery is pending, un-attempted, and carries the
        # emitted event and payload.
        for delivery in persisted:
            assert delivery.status == "pending"
            assert delivery.attempts == 0
            assert delivery.event == event
            assert delivery.payload == payload
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":  # pragma: no cover - convenience for ad-hoc runs
    pytest.main([__file__, "-v"])
