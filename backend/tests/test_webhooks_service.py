"""Unit tests for the webhook registration + emission service (task 14.1).

These tests exercise the service's core logic — event-subscription fan-out
(Property 18 essence), pending-delivery persistence, and the defensive enqueue
guard (R16.7) — without a Postgres database by emulating the small SQLAlchemy
``Session`` surface that ``emit`` relies on (``add``/``flush``/``execute``).

The dedicated transactional property tests for fan-out (task 14.2) and
emission-never-rolls-back (task 14.3) are separate.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.models.enums import WebhookEvent
from app.models.webhook import WebhookDelivery, WebhookEndpoint
from app.services import webhooks


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class FakeSession:
    """Minimal stand-in for a SQLAlchemy ``Session``.

    ``execute`` returns only the *active* endpoints (mirroring the SQL
    ``WHERE active`` predicate); ``flush`` assigns ids to freshly added rows so
    the service can enqueue by delivery id.
    """

    def __init__(self, endpoints):
        self._active_endpoints = [ep for ep in endpoints if ep.active]
        self.added: list = []

    def execute(self, _stmt):
        return FakeResult(self._active_endpoints)

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid4()


def _endpoint(events, *, active=True, company_id=None):
    return WebhookEndpoint(
        id=uuid4(),
        company_id=company_id,
        url="https://example.test/hook",
        secret="shh",
        events=list(events),
        active=active,
    )


@pytest.fixture()
def captured_enqueue(monkeypatch):
    """Capture enqueue calls instead of touching Redis."""
    calls: list[str] = []
    monkeypatch.setattr(webhooks, "_enqueue_delivery", lambda delivery_id: calls.append(delivery_id))
    return calls


def test_register_endpoint_normalises_and_dedupes_events():
    session = FakeSession([])
    endpoint = webhooks.register_endpoint(
        session,
        company_id=None,
        url="https://example.test/hook",
        secret="shh",
        events=[WebhookEvent.job_published, "job.published", WebhookEvent.application_created],
    )
    assert endpoint.events == ["job.published", "application.created"]
    assert endpoint.active is True
    assert endpoint in session.added


def test_emit_fans_out_to_subscribed_endpoints_only(captured_enqueue):
    subscribed_a = _endpoint([WebhookEvent.job_published.value])
    subscribed_b = _endpoint([WebhookEvent.job_published.value, WebhookEvent.application_created.value])
    other_event = _endpoint([WebhookEvent.application_created.value])
    inactive = _endpoint([WebhookEvent.job_published.value], active=False)

    session = FakeSession([subscribed_a, subscribed_b, other_event, inactive])
    webhooks.emit(session, WebhookEvent.job_published, {"id": "job-1"})

    deliveries = [obj for obj in session.added if isinstance(obj, WebhookDelivery)]
    delivered_endpoint_ids = {d.endpoint_id for d in deliveries}

    # Exactly the active, job.published-subscribed endpoints get a delivery.
    assert delivered_endpoint_ids == {subscribed_a.id, subscribed_b.id}
    assert all(d.status == "pending" and d.attempts == 0 for d in deliveries)
    assert all(d.event == WebhookEvent.job_published for d in deliveries)
    # One enqueue per persisted delivery.
    assert len(captured_enqueue) == len(deliveries) == 2


def test_emit_without_subscribers_persists_nothing(captured_enqueue):
    session = FakeSession([_endpoint([WebhookEvent.application_created.value])])
    webhooks.emit(session, WebhookEvent.job_published, {"id": "job-1"})
    assert [obj for obj in session.added if isinstance(obj, WebhookDelivery)] == []
    assert captured_enqueue == []


def test_enqueue_failure_never_raises(monkeypatch):
    """A failure while enqueuing must be swallowed so the persisted delivery is
    retained (R16.7). Drives the real ``_enqueue_delivery`` guard around a
    failing async enqueue."""

    async def _fail_async(delivery_id):
        raise RuntimeError("redis down")

    monkeypatch.setattr(webhooks, "_enqueue_delivery_async", _fail_async)

    endpoint = _endpoint([WebhookEvent.job_published.value])
    session = FakeSession([endpoint])
    # Should not raise even though the underlying enqueue fails.
    webhooks.emit(session, WebhookEvent.job_published, {"id": "job-1"})

    deliveries = [obj for obj in session.added if isinstance(obj, WebhookDelivery)]
    assert len(deliveries) == 1
