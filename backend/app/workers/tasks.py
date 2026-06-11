from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import select

from app.payments.settlement import coerce_pk, resolve_model, session_scope, settle_intent, utcnow

logger = logging.getLogger(__name__)


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
