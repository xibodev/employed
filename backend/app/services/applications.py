"""Application tracking service (R16).

A tracked :class:`Application` is the first-class record of a candidate applying
to a job. Each application carries *exactly one* candidate reference — either a
platform ``candidate_user_id`` or an inline ``candidate_snapshot`` (R16.2) — and
is created at the first pipeline stage, ``applied`` (R16.4).

After the row is persisted the Platform emits the ``application.created`` webhook
event (R16.6). Emission happens *after* persistence and is fully guarded: a
failure to emit (including the webhook service not being available yet) is logged
and swallowed so the persisted application is always retained (R16.7). The work
flushes within the caller's transaction (DD-10); the caller owns the final commit.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.enums import ApplicationStatus, WebhookEvent
from app.models.user import User
from app.services.audit import write_audit

logger = logging.getLogger(__name__)


def _emit_application_created(db: Session, application: Application) -> None:
    """Emit the ``application.created`` event for *application* (R16.6).

    Emission runs *after* the application is persisted and never rolls back the
    persisted row (R16.7). The webhook service (``app.services.webhooks``) may not
    be wired yet, so it is imported lazily; a missing service or any emission
    error is logged and swallowed rather than propagated.
    """
    payload: dict[str, Any] = {
        "id": str(application.id),
        "job_id": str(application.job_id),
        "company_id": str(application.company_id) if application.company_id is not None else None,
        "candidate_user_id": (
            str(application.candidate_user_id) if application.candidate_user_id is not None else None
        ),
        "candidate_snapshot": application.candidate_snapshot,
        "resume_version_id": (
            str(application.resume_version_id) if application.resume_version_id is not None else None
        ),
        "status": application.status.value,
        "source": application.source,
    }

    try:
        from app.services.webhooks import emit
    except ImportError:
        # The webhook service is not available yet; the application is already
        # persisted and must be retained regardless (R16.7).
        logger.warning(
            "Webhook service unavailable; skipped %s emission for application %s",
            WebhookEvent.application_created.value,
            application.id,
        )
        return

    try:
        emit(db, WebhookEvent.application_created, payload)
    except Exception:
        # Emission failure must never roll back the persisted application (R16.7).
        logger.exception(
            "Failed to emit %s for application %s",
            WebhookEvent.application_created.value,
            application.id,
        )


def create_application(
    db: Session,
    *,
    job_id: UUID,
    candidate_user_id: UUID | None = None,
    candidate_snapshot: dict[str, Any] | None = None,
    company_id: UUID | None = None,
    resume_version_id: UUID | None = None,
    cover_note: str | None = None,
    source: str = "platform",
) -> Application:
    """Create a tracked Application at status ``applied`` (R16.2/16.4/16.6/16.7).

    Exactly one candidate reference must be supplied: either *candidate_user_id*
    or *candidate_snapshot*, but not both and not neither (R16.2). The application
    is created at the first pipeline stage ``applied`` (R16.4) and flushed within
    the caller's transaction (DD-10) so its server-side id is assigned.

    After the row is persisted the ``application.created`` webhook event is
    emitted (R16.6). Emission is guarded so a failure never rolls back the
    persisted application (R16.7).

    Raises :class:`ValueError` when the candidate reference is missing or
    ambiguous. Returns the persisted ``Application``.
    """
    has_user = candidate_user_id is not None
    has_snapshot = candidate_snapshot is not None
    if has_user == has_snapshot:
        raise ValueError(
            "Exactly one candidate reference is required: provide either "
            "candidate_user_id or candidate_snapshot, not both and not neither."
        )

    application = Application(
        job_id=job_id,
        candidate_user_id=candidate_user_id,
        candidate_snapshot=candidate_snapshot,
        company_id=company_id,
        status=ApplicationStatus.applied,
        resume_version_id=resume_version_id,
        cover_note=cover_note,
        source=source,
    )
    db.add(application)
    db.flush()  # persist the row and assign application.id before emission

    _emit_application_created(db, application)

    return application


def _emit_application_status_changed(
    db: Session,
    application: Application,
    *,
    previous_status: ApplicationStatus,
) -> None:
    """Emit the ``application.status_changed`` event for *application* (R17.4).

    Emission runs *after* the new pipeline stage is persisted and never rolls
    back the persisted change (Property 19). The webhook service
    (``app.services.webhooks``) may not be wired yet, so it is imported lazily; a
    missing service or any emission error is logged and swallowed rather than
    propagated.
    """
    payload: dict[str, Any] = {
        "id": str(application.id),
        "job_id": str(application.job_id),
        "company_id": str(application.company_id) if application.company_id is not None else None,
        "candidate_user_id": (
            str(application.candidate_user_id) if application.candidate_user_id is not None else None
        ),
        "previous_status": previous_status.value,
        "status": application.status.value,
    }

    try:
        from app.services.webhooks import emit
    except ImportError:
        # The webhook service is not available yet; the status change is already
        # persisted and must be retained regardless (Property 19).
        logger.warning(
            "Webhook service unavailable; skipped %s emission for application %s",
            WebhookEvent.application_status_changed.value,
            application.id,
        )
        return

    try:
        emit(db, WebhookEvent.application_status_changed, payload)
    except Exception:
        # Emission failure must never roll back the persisted status change.
        logger.exception(
            "Failed to emit %s for application %s",
            WebhookEvent.application_status_changed.value,
            application.id,
        )


def change_status(
    db: Session,
    *,
    application: Application,
    new_status: ApplicationStatus,
    actor: User,
) -> Application:
    """Advance an Application to *new_status* in the hiring pipeline (R17.3/17.4/17.5).

    The application is updated to the new pipeline stage and the change is
    flushed within the caller's transaction (DD-10); the caller owns the final
    commit. An append-only audit-log entry recording the before/after status is
    written (R17.5), and the ``application.status_changed`` webhook event is
    emitted (R17.4). Emission is guarded so a failure never rolls back the
    persisted status change (Property 19).

    Returns the updated ``Application``.
    """
    previous_status = application.status

    application.status = new_status
    db.add(application)
    db.flush()  # persist the new pipeline stage before audit + emission

    write_audit(
        db,
        actor=actor,
        action=WebhookEvent.application_status_changed.value,
        target_type="application",
        target_id=application.id,
        before={"status": previous_status.value},
        after={"status": new_status.value},
    )

    _emit_application_status_changed(db, application, previous_status=previous_status)

    return application
