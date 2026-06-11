from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.payments.settlement import coerce_pk, resolve_model, settle_intent, utcnow
from app.webhooks.replay_cache import ReplayCache

logger = logging.getLogger(__name__)
router = APIRouter(tags=["webhooks"])

CALLBACK_REPLAY_WINDOW = timedelta(minutes=5)
PROCESSED_CALLBACK_EVENTS = ReplayCache(
    ttl_seconds=int(CALLBACK_REPLAY_WINDOW.total_seconds()),
    max_entries=10000,
    namespace="mobile-money",
)
TIMESTAMP_FIELDS = ("timestamp", "created_at", "createdAt", "sent_at", "sentAt")
EVENT_ID_FIELDS = (
    "event_id",
    "eventId",
    "nonce",
    "nonce_id",
    "nonceId",
    "callback_id",
    "callbackId",
    "request_id",
    "requestId",
)
EVENT_TYPE_FIELDS = ("event_type", "eventType", "type")


def _setting(name: str, default=None):
    return getattr(settings, name.lower(), getattr(settings, name, default))


def _verify_signature(raw_body: bytes, signature: str | None, secret: str | None, provider: str) -> None:
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"{provider}-webhook-secret-missing"
        )
    if not signature:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"missing-{provider}-signature")

    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"invalid-{provider}-signature")


def _normalize_status(value: str | None) -> str:
    normalized = (value or "pending").strip().lower()
    if normalized in {"success", "successful", "paid"}:
        return "completed"
    if normalized in {"error", "declined"}:
        return "failed"
    if normalized in {"timeout", "timed_out"}:
        return "failed"
    return normalized


def _extract_payload_fields(payload: dict) -> tuple[str | None, str | None, str, str | None]:
    provider_ref = (
        payload.get("provider_ref")
        or payload.get("providerRef")
        or payload.get("transactionId")
        or payload.get("conversationId")
    )
    intent_id = payload.get("intent_id") or payload.get("intentId")
    status_value = payload.get("status") or payload.get("transactionStatus") or payload.get("resultCode")
    reason = (
        payload.get("failure_reason")
        or payload.get("failureReason")
        or payload.get("resultDesc")
        or payload.get("message")
    )
    return provider_ref, intent_id, _normalize_status(str(status_value) if status_value is not None else None), reason


def _find_intent(db: Session, provider_ref: str | None, intent_id: str | None):
    PaymentIntent = resolve_model("PaymentIntent", ["payment_intent", "payment_intents"])
    if intent_id:
        intent = db.get(PaymentIntent, coerce_pk(intent_id))
        if intent is not None:
            return intent
    if provider_ref:
        stmt = (
            select(PaymentIntent)
            .where(PaymentIntent.provider_ref == provider_ref)
            .order_by(desc(PaymentIntent.created_at))
        )
        return db.execute(stmt).scalars().first()
    return None


def _parse_timestamp(value) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        numeric = float(text)
    except ValueError:
        numeric = None
    if numeric is not None and text.replace(".", "", 1).isdigit():
        return datetime.fromtimestamp(numeric, tz=timezone.utc)
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _extract_timestamp(payload: dict) -> tuple[str | None, datetime | None]:
    for field in TIMESTAMP_FIELDS:
        if field not in payload:
            continue
        try:
            return field, _parse_timestamp(payload.get(field))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid-webhook-timestamp") from exc
    return None, None


def _validate_timestamp(payload: dict) -> tuple[str | None, datetime | None]:
    field, timestamp_value = _extract_timestamp(payload)
    if timestamp_value is None:
        # EMP-019: payloads without any timestamp previously skipped staleness
        # validation entirely, leaving an unbounded replay window for captured
        # signed payloads. A timestamp field is now mandatory.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing-webhook-timestamp")
    if timestamp_value < utcnow() - CALLBACK_REPLAY_WINDOW:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="stale-webhook-payload")
    return field, timestamp_value


def _event_identifier(payload: dict, raw_body: bytes) -> str:
    for field in EVENT_ID_FIELDS:
        value = payload.get(field)
        if value:
            return f"{field}:{value}"
    return f"body:{hashlib.sha256(raw_body).hexdigest()}"


def _event_type(payload: dict) -> str:
    for field in EVENT_TYPE_FIELDS:
        value = payload.get(field)
        if value:
            return str(value)
    return "callback"


async def _handle_callback(provider: str, request: Request, db: Session, secret: str | None) -> dict:
    raw_body = await request.body()
    signature = request.headers.get(f"x-{provider}-signature") or request.headers.get("x-callback-signature")
    _verify_signature(raw_body, signature, secret, provider)

    payload = json.loads(raw_body.decode("utf-8") or "{}")
    timestamp_field, timestamp_value = _validate_timestamp(payload)
    replay_key = _event_identifier(payload, raw_body)
    event_type = _event_type(payload)
    provider_ref, intent_id, status_value, reason = _extract_payload_fields(payload)

    logger.info(
        "%s.webhook.received event_type=%s replay_key=%s provider_ref=%s intent_id=%s status=%s timestamp_field=%s timestamp=%s",
        provider,
        event_type,
        replay_key,
        provider_ref,
        intent_id,
        status_value,
        timestamp_field,
        timestamp_value.isoformat() if timestamp_value else None,
    )

    cache_key = f"{provider}:{replay_key}"
    if PROCESSED_CALLBACK_EVENTS.contains(cache_key):
        logger.info("%s.webhook.duplicate replay_key=%s event_type=%s", provider, replay_key, event_type)
        return {"ok": True, "updated": False}

    intent = _find_intent(db, provider_ref, intent_id)
    if intent is None:
        logger.warning(
            "%s.webhook.intent_not_found event_type=%s replay_key=%s provider_ref=%s intent_id=%s",
            provider,
            event_type,
            replay_key,
            provider_ref,
            intent_id,
        )
        PROCESSED_CALLBACK_EVENTS.add(cache_key)
        return {"ok": True, "updated": False}

    if provider_ref:
        intent.provider_ref = provider_ref

    if status_value == "completed":
        await settle_intent(db, str(intent.id), provider_ref=provider_ref)
    else:
        intent.status = status_value
        intent.failure_reason = reason if status_value == "failed" else None
        if status_value in {"failed", "cancelled", "expired"}:
            intent.settled_at = utcnow()
        if hasattr(intent, "updated_at"):
            intent.updated_at = utcnow()
        db.add(intent)
        db.commit()

    logger.info(
        "%s.webhook.processed event_type=%s replay_key=%s intent_id=%s provider_ref=%s status=%s",
        provider,
        event_type,
        replay_key,
        intent.id,
        provider_ref,
        status_value,
    )
    PROCESSED_CALLBACK_EVENTS.add(cache_key)
    return {"ok": True, "updated": True}


@router.post("/_mpesa/callback", include_in_schema=False)
async def mpesa_callback(request: Request, db: Session = Depends(get_db)) -> dict:
    return await _handle_callback("mpesa", request, db, _setting("MPESA_WEBHOOK_SECRET"))


@router.post("/_emola/callback", include_in_schema=False)
async def emola_callback(request: Request, db: Session = Depends(get_db)) -> dict:
    return await _handle_callback("emola", request, db, _setting("EMOLA_WEBHOOK_SECRET"))
