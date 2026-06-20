"""Outbound webhook registration and emission (R20).

A :class:`~app.models.webhook.WebhookEndpoint` is a registered receiver for
domain events. ``company_id`` is nullable so platform-level endpoints can
subscribe without being scoped to a single tenant. ``events`` is the set of
:class:`~app.models.enums.WebhookEvent` values an endpoint is subscribed to.

:func:`emit` fans an event out to *exactly* the active endpoints subscribed to
that event (Property 18): it persists one :class:`~app.models.webhook.WebhookDelivery`
row per subscribed endpoint (status ``pending``) and enqueues the ``deliver_webhook``
arq task per delivery.

Emission is designed to run *after* the triggering business write has been
flushed/committed and must never roll back that write (R16.7): delivery rows are
persisted within the caller's transaction (DD-10), and enqueue failures are
logged and swallowed so a persisted delivery is never lost. The actual
``deliver_webhook`` task (task 14.4) is referenced by name only, so this module
does not hard-depend on it existing yet.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.enums import WebhookEvent
from app.models.webhook import WebhookDelivery, WebhookEndpoint

logger = logging.getLogger(__name__)

DELIVER_WEBHOOK_TASK = "deliver_webhook"


def _setting(name: str, default: Any = None) -> Any:
    """Read a setting tolerating either lower/upper attribute casing."""
    value = getattr(settings, name.lower(), None)
    if value in (None, ""):
        value = getattr(settings, name, None)
    if value in (None, ""):
        value = default
    return value


def register_endpoint(
    db: Session,
    *,
    company_id: UUID | None,
    url: str,
    secret: str,
    events: Iterable[str | WebhookEvent],
    active: bool = True,
) -> WebhookEndpoint:
    """Register a webhook endpoint subscribed to *events* (R20.4).

    *company_id* may be ``None`` for a platform-level endpoint. *events* is
    normalised to the underlying :class:`WebhookEvent` string values and
    de-duplicated while preserving order. The endpoint is flushed within the
    caller's transaction (DD-10) so its server-side id is assigned; the caller
    owns the final commit.
    """
    normalised: list[str] = []
    for event in events:
        value = event.value if isinstance(event, WebhookEvent) else str(event)
        if value not in normalised:
            normalised.append(value)

    endpoint = WebhookEndpoint(
        company_id=company_id,
        url=url,
        secret=secret,
        events=normalised,
        active=active,
    )
    db.add(endpoint)
    db.flush()  # assign endpoint.id before returning
    return endpoint


def _subscribed_endpoints(db: Session, event: WebhookEvent) -> list[WebhookEndpoint]:
    """Return active endpoints subscribed to *event* (company-scoped and
    platform-level alike). Fan-out is determined purely by event subscription:
    an endpoint is included iff it is active and *event* is in its ``events``
    list, and excluded otherwise (Property 18)."""
    endpoints = db.execute(select(WebhookEndpoint).where(WebhookEndpoint.active.is_(True))).scalars().all()
    return [endpoint for endpoint in endpoints if event.value in (endpoint.events or [])]


def _enqueue_delivery(delivery_id: str) -> None:
    """Best-effort enqueue of the ``deliver_webhook`` task for *delivery_id*.

    The task is referenced by name (it lands in task 14.4) so this module does
    not hard-depend on it. Any failure — Redis unavailable, arq missing, or no
    usable event loop — is logged and swallowed: the delivery row is already
    persisted and a later sweep/retry can pick it up, so an enqueue failure must
    never lose the persisted delivery (R16.7).
    """
    try:
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            # Already inside an event loop (async caller): schedule and return.
            loop.create_task(_enqueue_delivery_async(delivery_id))
        else:
            asyncio.run(_enqueue_delivery_async(delivery_id))
    except Exception:
        logger.exception("Failed to enqueue %s for delivery %s", DELIVER_WEBHOOK_TASK, delivery_id)


async def _enqueue_delivery_async(delivery_id: str) -> None:
    from arq import create_pool
    from arq.connections import RedisSettings

    redis = await create_pool(RedisSettings.from_dsn(_setting("REDIS_URL", "redis://localhost:6379/0")))
    try:
        await redis.enqueue_job(DELIVER_WEBHOOK_TASK, delivery_id)
    finally:
        await redis.close()


def emit(db: Session, event: WebhookEvent, payload: dict) -> list[WebhookDelivery]:
    """Persist one ``WebhookDelivery`` per subscribed endpoint and enqueue
    delivery (R20.1/20.2/20.3/20.4).

    Fans *event* out to exactly the active endpoints subscribed to it and no
    others (Property 18). For each, a ``pending`` :class:`WebhookDelivery` is
    persisted (flushed within the caller's transaction, DD-10) and the
    ``deliver_webhook`` task is enqueued. Returns the persisted deliveries (one
    per subscribed endpoint, empty when nothing is subscribed) so callers and
    property tests can assert the fan-out.

    This is intended to be called *after* the triggering business write has been
    flushed/committed; it never rolls back that write (R16.7). Enqueue failures
    are logged and swallowed so a persisted delivery is never lost.
    """
    endpoints = _subscribed_endpoints(db, event)
    if not endpoints:
        return []

    deliveries: list[WebhookDelivery] = []
    for endpoint in endpoints:
        delivery = WebhookDelivery(
            endpoint_id=endpoint.id,
            event=event,
            payload=dict(payload),
            status="pending",
            attempts=0,
        )
        db.add(delivery)
        deliveries.append(delivery)

    db.flush()  # assign delivery ids before enqueue

    for delivery in deliveries:
        _enqueue_delivery(str(delivery.id))

    logger.info(
        "webhooks.emit event=%s endpoints=%s deliveries=%s",
        event.value,
        len(endpoints),
        len(deliveries),
    )
    return deliveries
