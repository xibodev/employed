from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import timedelta

import httpx
from sqlalchemy import select

from app.payments.settlement import coerce_pk, resolve_model, session_scope, settle_intent, utcnow
from app.services.export import to_json_resume
from app.services.resume_templates import (
    DEFAULT_RESUME_TEMPLATE_ID,
    ProfileVersionNotFoundError,
    build_resume_artifact,
)

logger = logging.getLogger(__name__)

# Webhook delivery retry policy (R20.5 / Property 20).
#
# After each failed attempt the next retry is scheduled ``min(2**attempts *
# WEBHOOK_BACKOFF_BASE_SECONDS, WEBHOOK_BACKOFF_CAP)`` into the future, where
# ``attempts`` is the number of attempts made so far. This yields a
# monotonically non-decreasing schedule that is bounded above by the cap. Once
# ``WEBHOOK_MAX_ATTEMPTS`` is reached the delivery transitions to the terminal
# ``failed`` state and is not retried further.
WEBHOOK_BACKOFF_BASE_SECONDS = 30
WEBHOOK_BACKOFF_CAP = timedelta(hours=6)
WEBHOOK_MAX_ATTEMPTS = 10
WEBHOOK_DELIVERY_TIMEOUT_SECONDS = 10.0
_WEBHOOK_LAST_ERROR_MAX_LEN = 1000


def compute_backoff_delay(attempts: int) -> timedelta:
    """Return the delay before the next delivery attempt (R20.5 / Property 20).

    *attempts* is the number of delivery attempts already made. The delay grows
    exponentially (``2**attempts`` times the base interval) but is clamped to
    :data:`WEBHOOK_BACKOFF_CAP`, so the schedule is monotonically non-decreasing
    in *attempts* and bounded above by the cap. Non-positive *attempts* are
    treated as ``0`` (the minimum, base, delay).
    """
    safe_attempts = max(int(attempts), 0)
    # Cap the exponent before shifting so very large attempt counts cannot
    # overflow into an enormous intermediate value; the result is clamped anyway.
    capped_exponent = min(safe_attempts, 32)
    raw_seconds = (2**capped_exponent) * WEBHOOK_BACKOFF_BASE_SECONDS
    delay = timedelta(seconds=raw_seconds)
    return delay if delay < WEBHOOK_BACKOFF_CAP else WEBHOOK_BACKOFF_CAP


async def expire_old_jobs(ctx):
    """Run hourly. Expire active jobs older than 90 days.

    JobStatus has no 'expired' member, so the status maps to 'inactive' —
    but the transition is now recorded in status_history with reason
    'expired' so expired listings stay distinguishable from
    owner-deactivated ones without an enum migration (EMP-017).
    """

    Job = resolve_model("Job", ["job", "jobs"])
    cutoff = utcnow() - timedelta(days=90)
    expired = 0

    with session_scope() as db:
        stmt = select(Job).where(Job.status == "active", Job.created_at < cutoff)
        jobs = db.execute(stmt).scalars().all()
        now = utcnow()
        try:
            from app.models.enums import JobStatus

            expired_status = getattr(JobStatus, "expired", JobStatus.inactive)
        except Exception:
            expired_status = "expired"
        for job in jobs:
            previous_status = getattr(job, "status", None)
            job.status = expired_status
            if hasattr(job, "status_history"):
                history = list(job.status_history or [])
                history.append(
                    {
                        "at": now.isoformat(),
                        "by": "worker:expire_old_jobs",
                        "from": str(getattr(previous_status, "value", previous_status)),
                        "to": str(getattr(expired_status, "value", expired_status)),
                        "reason": "expired (90-day listing window)",
                    }
                )
                job.status_history = history[-100:]
            if hasattr(job, "expired_at"):
                job.expired_at = now
            if hasattr(job, "updated_at"):
                job.updated_at = now
            expired += 1
            db.add(job)
        db.commit()

    logger.info("workers.expire_old_jobs count=%s", expired)
    return expired


async def delete_scheduled_accounts(ctx):
    """Run hourly. Find users where deletion_scheduled_for < now(). Delete their jobs, profiles, and user record."""

    User = resolve_model("User", ["user", "users"])
    Job = resolve_model("Job", ["job", "jobs"])
    try:
        Profile = resolve_model("Profile", ["profile", "profiles"])
    except Exception:
        Profile = None

    deleted = 0
    now = utcnow()

    with session_scope() as db:
        users = db.execute(select(User).where(User.deletion_scheduled_for < now)).scalars().all()
        for user in users:
            user_id = getattr(user, "id")
            jobs = db.execute(select(Job).where(Job.user_id == user_id)).scalars().all()
            for job in jobs:
                db.delete(job)
            if Profile is not None and hasattr(Profile, "user_id"):
                profiles = db.execute(select(Profile).where(Profile.user_id == user_id)).scalars().all()
                for profile in profiles:
                    db.delete(profile)
            db.delete(user)
            deleted += 1
            logger.warning("workers.delete_scheduled_accounts.deleted user_id=%s jobs=%s", user_id, len(jobs))
        db.commit()

    return deleted


async def settle_simulated_intent(ctx, intent_id: str, outcome_status: str, outcome_reason: str | None = None):
    """Called by M-Pesa/e-Mola simulator after delay."""

    PaymentIntent = resolve_model("PaymentIntent", ["payment_intent", "payment_intents"])
    with session_scope() as db:
        intent = db.get(PaymentIntent, coerce_pk(intent_id))
        if intent is None:
            logger.warning("workers.settle_simulated_intent.missing intent_id=%s", intent_id)
            return None

        if outcome_status == "completed":
            return await settle_intent(db, intent_id, provider_ref=getattr(intent, "provider_ref", None))

        intent.status = "failed"
        intent.failure_reason = outcome_reason or "unknown"
        intent.settled_at = utcnow()
        if hasattr(intent, "updated_at"):
            intent.updated_at = intent.settled_at
        db.add(intent)
        db.commit()
        logger.info(
            "workers.settle_simulated_intent.failed intent_id=%s provider_ref=%s reason=%s",
            intent_id,
            getattr(intent, "provider_ref", None),
            intent.failure_reason,
        )
        return intent


async def render_resume_pdf(
    ctx,
    profile_version_id: str,
    template_id: str = DEFAULT_RESUME_TEMPLATE_ID,
    artifact_dir: str | None = None,
):
    """Render a downloadable PDF resume for a ProfileVersion server-side (R14.2/14.3).

    Loads the requested ``ProfileVersion``, maps it to a JSON Resume document via
    :func:`app.services.export.to_json_resume`, renders the chosen
    ``Resume_Template`` to a PDF artifact, and returns a JSON-serialisable
    download reference.

    Raises :class:`ProfileVersionNotFoundError` when the ``ProfileVersion`` does
    not exist so the enqueuing endpoint can surface a ``404`` (R14.4).
    """

    ProfileVersion = resolve_model("ProfileVersion", ["profile_version", "profile_versions"])

    with session_scope() as db:
        version = db.get(ProfileVersion, coerce_pk(profile_version_id))
        if version is None:
            logger.warning("workers.render_resume_pdf.not_found profile_version_id=%s", profile_version_id)
            raise ProfileVersionNotFoundError(str(profile_version_id))
        json_resume = to_json_resume(version)

    artifact = build_resume_artifact(
        json_resume,
        template_id=template_id,
        profile_version_id=str(profile_version_id),
        artifact_dir=artifact_dir,
    )

    logger.info(
        "workers.render_resume_pdf.rendered profile_version_id=%s template_id=%s size_bytes=%s",
        profile_version_id,
        artifact["template_id"],
        artifact["size_bytes"],
    )
    return artifact


def _sign_payload(secret: str | None, body: bytes) -> str | None:
    """Return a hex HMAC-SHA256 signature of *body* using *secret*, or ``None``.

    Receivers can verify authenticity by recomputing the HMAC over the raw
    request body with their shared endpoint secret.
    """
    if not secret:
        return None
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


async def _post_webhook(url: str, body: bytes, signature: str | None) -> int:
    """POST *body* to *url* and return the HTTP status code.

    Raises on transport errors and non-2xx responses so the caller can record a
    failed attempt. Isolated from :func:`deliver_webhook` so tests can mock the
    outbound HTTP call.
    """
    headers = {"Content-Type": "application/json"}
    if signature is not None:
        headers["X-Webhook-Signature"] = f"sha256={signature}"

    async with httpx.AsyncClient(timeout=WEBHOOK_DELIVERY_TIMEOUT_SECONDS) as client:
        response = await client.post(url, content=body, headers=headers)
        response.raise_for_status()
        return response.status_code


async def deliver_webhook(ctx, delivery_id: str):
    """Deliver a ``WebhookDelivery`` to its endpoint with bounded backoff retry (R20.5).

    Loads the delivery and its endpoint, POSTs the payload, and on success marks
    the delivery ``delivered``. On failure it increments ``attempts``, records
    ``last_error``, and either schedules the next retry via
    :func:`compute_backoff_delay` (staying ``pending``) or, once
    :data:`WEBHOOK_MAX_ATTEMPTS` is reached, transitions to the terminal
    ``failed`` state (Property 20).

    Returns a small JSON-serialisable summary of the outcome, or ``None`` when
    the delivery does not exist (logged, 404-equivalent).
    """
    WebhookDelivery = resolve_model("WebhookDelivery", ["webhook"])
    WebhookEndpoint = resolve_model("WebhookEndpoint", ["webhook"])

    with session_scope() as db:
        delivery = db.get(WebhookDelivery, coerce_pk(delivery_id))
        if delivery is None:
            logger.warning("workers.deliver_webhook.not_found delivery_id=%s", delivery_id)
            return None

        # Idempotent: a delivery that already succeeded is never re-sent, and a
        # terminally failed one is not retried.
        if delivery.status in ("delivered", "failed"):
            logger.info(
                "workers.deliver_webhook.skip delivery_id=%s status=%s",
                delivery_id,
                delivery.status,
            )
            return {"delivery_id": str(delivery_id), "status": delivery.status, "attempts": delivery.attempts}

        endpoint = db.get(WebhookEndpoint, coerce_pk(delivery.endpoint_id))
        if endpoint is None:
            delivery.status = "failed"
            delivery.last_error = "endpoint not found"
            delivery.next_attempt_at = None
            db.add(delivery)
            db.commit()
            logger.warning(
                "workers.deliver_webhook.endpoint_missing delivery_id=%s endpoint_id=%s",
                delivery_id,
                delivery.endpoint_id,
            )
            return {"delivery_id": str(delivery_id), "status": "failed", "attempts": delivery.attempts}

        body = json.dumps(delivery.payload or {}, separators=(",", ":"), sort_keys=True).encode("utf-8")
        signature = _sign_payload(getattr(endpoint, "secret", None), body)

        try:
            status_code = await _post_webhook(endpoint.url, body, signature)
        except Exception as exc:  # transport error or non-2xx response
            delivery.attempts += 1
            delivery.last_error = str(exc)[:_WEBHOOK_LAST_ERROR_MAX_LEN]
            if delivery.attempts >= WEBHOOK_MAX_ATTEMPTS:
                delivery.status = "failed"
                delivery.next_attempt_at = None
                logger.warning(
                    "workers.deliver_webhook.failed delivery_id=%s attempts=%s error=%s",
                    delivery_id,
                    delivery.attempts,
                    delivery.last_error,
                )
            else:
                delivery.status = "pending"
                delivery.next_attempt_at = utcnow() + compute_backoff_delay(delivery.attempts)
                logger.info(
                    "workers.deliver_webhook.retry delivery_id=%s attempts=%s next_attempt_at=%s",
                    delivery_id,
                    delivery.attempts,
                    delivery.next_attempt_at.isoformat(),
                )
            db.add(delivery)
            db.commit()
            return {
                "delivery_id": str(delivery_id),
                "status": delivery.status,
                "attempts": delivery.attempts,
            }

        delivery.status = "delivered"
        delivery.last_error = None
        delivery.next_attempt_at = None
        db.add(delivery)
        db.commit()
        logger.info(
            "workers.deliver_webhook.delivered delivery_id=%s status_code=%s attempts=%s",
            delivery_id,
            status_code,
            delivery.attempts,
        )
        return {"delivery_id": str(delivery_id), "status": "delivered", "attempts": delivery.attempts}
