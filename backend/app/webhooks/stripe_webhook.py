from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.payments.settlement import coerce_pk, resolve_model, settle_intent, utcnow
from app.webhooks.replay_cache import ReplayCache

logger = logging.getLogger(__name__)
router = APIRouter(tags=["webhooks"])

PROCESSED_STRIPE_EVENTS = ReplayCache(ttl_seconds=86400, max_entries=10000, namespace="stripe")


def _setting(name: str, default=None):
    return getattr(settings, name.lower(), getattr(settings, name, default))


def _stripe_module():
    import stripe

    stripe.api_key = _setting("STRIPE_SECRET_KEY")
    return stripe


def _find_intent_from_session(db: Session, session_payload: dict):
    PaymentIntent = resolve_model("PaymentIntent", ["payment_intent", "payment_intents"])
    metadata = session_payload.get("metadata") or {}

    intent_id = metadata.get("intentId") or metadata.get("intent_id")
    if intent_id:
        intent = db.get(PaymentIntent, coerce_pk(intent_id))
        if intent is not None:
            return intent

    provider_ref = session_payload.get("id")
    if provider_ref:
        stmt = (
            select(PaymentIntent)
            .where(PaymentIntent.provider_ref == provider_ref)
            .order_by(desc(PaymentIntent.created_at))
        )
        intent = db.execute(stmt).scalars().first()
        if intent is not None:
            return intent

    job_id = metadata.get("jobId") or metadata.get("job_id")
    if not job_id:
        return None

    stmt = select(PaymentIntent).where(PaymentIntent.job_id == job_id).order_by(desc(PaymentIntent.created_at))
    return db.execute(stmt).scalars().first()


@router.post("/_stripe/webhook", include_in_schema=False)
async def stripe_webhook(request: Request, db: Session = Depends(get_db)) -> Response:
    if not _setting("STRIPE_WEBHOOK_SECRET"):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="stripe-webhook-secret-missing")

    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    if not signature:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing-stripe-signature")

    stripe = _stripe_module()
    try:
        event = stripe.Webhook.construct_event(payload, signature, _setting("STRIPE_WEBHOOK_SECRET"))
    except Exception as exc:  # pragma: no cover - provider library error shape varies
        logger.warning("stripe.webhook.bad_signature error=%s", exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid-stripe-signature") from exc

    event_id = event.get("id")
    event_type = event["type"]
    data_object = event["data"]["object"]
    metadata = data_object.get("metadata") or {}
    intent_id = metadata.get("intentId") or metadata.get("intent_id")
    session_id = data_object.get("id")

    logger.info(
        "stripe.webhook.received event_id=%s event_type=%s session_id=%s intent_id=%s",
        event_id,
        event_type,
        session_id,
        intent_id,
    )

    if PROCESSED_STRIPE_EVENTS.contains(event_id):
        logger.info("stripe.webhook.duplicate event_id=%s event_type=%s", event_id, event_type)
        return Response(content="ok", media_type="text/plain")

    if event_type in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
        intent = _find_intent_from_session(db, data_object)
        if intent is None:
            logger.warning(
                "stripe.webhook.intent_not_found event_id=%s event_type=%s session_id=%s intent_id=%s",
                event_id,
                event_type,
                session_id,
                intent_id,
            )
        else:
            await settle_intent(db, str(intent.id), provider_ref=session_id)
    elif event_type == "checkout.session.async_payment_failed":
        intent = _find_intent_from_session(db, data_object)
        if intent is not None:
            intent.status = "failed"
            intent.failure_reason = data_object.get("payment_status") or "async_payment_failed"
            intent.settled_at = utcnow()
            if hasattr(intent, "updated_at"):
                intent.updated_at = intent.settled_at
            db.add(intent)
            db.commit()
            logger.info(
                "stripe.webhook.failed event_id=%s event_type=%s session_id=%s intent_id=%s",
                event_id,
                event_type,
                session_id,
                intent.id,
            )
    elif event_type == "charge.refunded":
        logger.warning("stripe.webhook.charge_refunded event_id=%s charge_id=%s", event_id, data_object.get("id"))
    elif event_type == "charge.dispute.created":
        logger.warning(
            "stripe.webhook.charge_dispute_created event_id=%s dispute_charge_id=%s",
            event_id,
            data_object.get("id"),
        )

    PROCESSED_STRIPE_EVENTS.add(event_id)
    return Response(content="ok", media_type="text/plain")
