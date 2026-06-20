from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.auth.dependencies import get_primary_email, get_user_id, get_user_roles, is_email_verified, require_admin
from app.database import get_db
from app.schemas.jobs import JobListResponse
from app.schemas.reports import ReportRead
from app.schemas.users import UserRead
from app.services.model_utils import (
    get_attr,
    get_by_id,
    get_model_field,
    query_all,
    resolve_model,
    save,
    set_attr,
    utcnow,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

VALID_STATUSES = {"pending", "active", "flagged", "inactive", "filled"}
VALID_RESOLUTIONS = {"pending", "reviewed", "dismissed", "job_removed"}


def _emit_job_published(db: Any, job: Any) -> None:
    """Emit the ``job.published`` webhook event for *job* (R20.1).

    Called after a job becomes ``active`` and the transition is persisted.
    Emission is fully guarded: the webhook service may not be wired yet and any
    emission failure is logged and swallowed so it never breaks job publication
    (R16.7-style guarantee).
    """
    from app.models.enums import WebhookEvent

    payload = {
        "id": str(get_attr(job, "id", default="") or ""),
        "company_id": (
            str(get_attr(job, "company_id", "companyId"))
            if get_attr(job, "company_id", "companyId") is not None
            else None
        ),
        "title": get_attr(job, "title"),
        "status": get_attr(job, "status"),
        "country": get_attr(job, "country"),
        "published_at": (
            published.isoformat()
            if (published := get_attr(job, "published_at", "publishedAt")) is not None
            and hasattr(published, "isoformat")
            else get_attr(job, "published_at", "publishedAt")
        ),
    }

    try:
        from app.services.webhooks import emit
    except ImportError:
        logger.warning("Webhook service unavailable; skipped job.published emission for job %s", payload["id"])
        return

    try:
        emit(db, WebhookEvent.job_published, payload)
    except Exception:
        logger.exception("Failed to emit job.published for job %s", payload["id"])


def _pushdown_admin_jobs(db: Any, model: Any, status_filter: str | None) -> list[Any]:
    """Push admin /jobs WHERE/ORDER BY to the DB; fall back to a full scan."""
    status_field = get_model_field(model, "status")
    created_field = get_model_field(model, "created_at", "createdAt")
    if status_field is not None or created_field is not None:
        filters = [status_field == status_filter] if (status_filter and status_field is not None) else []
        order_by = created_field.desc() if created_field is not None else None
        items = query_all(db, model, filters=filters or None, order_by=order_by)
        if status_filter and status_field is None:
            items = [item for item in items if get_attr(item, "status") == status_filter]
        return items
    items = query_all(db, model)
    if status_filter:
        items = [item for item in items if get_attr(item, "status") == status_filter]
    items.sort(key=lambda item: get_attr(item, "created_at", "createdAt", default=utcnow()), reverse=True)
    return items


def _pushdown_admin_reports(db: Any, model: Any, resolution: str | None) -> list[Any]:
    resolution_field = get_model_field(model, "resolution")
    created_field = get_model_field(model, "created_at", "createdAt")
    if resolution_field is not None or created_field is not None:
        filters = [resolution_field == resolution] if (resolution and resolution_field is not None) else []
        order_by = created_field.desc() if created_field is not None else None
        items = query_all(db, model, filters=filters or None, order_by=order_by, limit=200)
        if resolution and resolution_field is None:
            items = [item for item in items if get_attr(item, "resolution") == resolution]
        return items
    items = query_all(db, model)
    if resolution:
        items = [item for item in items if get_attr(item, "resolution") == resolution]
    items.sort(key=lambda item: get_attr(item, "created_at", "createdAt", default=utcnow()), reverse=True)
    return items[:200]


class JobStatusUpdate(BaseModel):
    status: str
    reason: str | None = None


class BulkStatusUpdate(BaseModel):
    job_ids: list[str] = Field(min_length=1, max_length=200)
    status: str
    reason: str | None = None


class BulkStatusResult(BaseModel):
    requested: int
    updated: int


@router.get("/jobs", response_model=JobListResponse)
def admin_jobs(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Any = Depends(get_db),
    admin_user: Any = Depends(require_admin),
):
    from app.routers.jobs import _job_model, _job_to_read

    items = _pushdown_admin_jobs(db, _job_model(), status_filter)
    start = (page - 1) * page_size
    end = start + page_size
    return JobListResponse(
        items=[_job_to_read(item, request) for item in items[start:end]],
        total=len(items),
        page=page,
        page_size=page_size,
    )


@router.patch("/jobs/{job_id}/status")
def set_job_status(
    job_id: str,
    payload: JobStatusUpdate,
    db: Any = Depends(get_db),
    admin_user: Any = Depends(require_admin),
):
    job_model = resolve_model("Job", "Jobs")
    job = get_by_id(db, job_model, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if payload.status not in VALID_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status")
    history = list(get_attr(job, "status_history", "statusHistory", default=[]) or [])
    history.append(
        {
            "at": utcnow().isoformat(),
            "by": str(get_user_id(admin_user) or ""),
            "from": get_attr(job, "status"),
            "to": payload.status,
            "reason": payload.reason,
        }
    )
    history = history[-100:]
    previous_status = get_attr(job, "status")
    set_attr(job, payload.status, "status")
    set_attr(job, history, "status_history", "statusHistory")
    becomes_published = payload.status == "active" and previous_status != "active"
    if payload.status == "active" and get_attr(job, "published_at", "publishedAt") is None:
        set_attr(job, utcnow(), "published_at", "publishedAt")
    set_attr(job, utcnow(), "updated_at", "updatedAt")
    saved = save(db, job)
    if becomes_published:
        _emit_job_published(db, saved)
    return {"job_id": job_id, "status": get_attr(saved, "status")}


@router.patch("/jobs/bulk-status", response_model=BulkStatusResult)
def bulk_set_status(
    payload: BulkStatusUpdate,
    db: Any = Depends(get_db),
    admin_user: Any = Depends(require_admin),
):
    if payload.status not in VALID_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status")
    payload.job_ids = list(dict.fromkeys(payload.job_ids))
    updated = 0
    for job_id in payload.job_ids[:200]:
        job = get_by_id(db, resolve_model("Job", "Jobs"), job_id)
        if job is None:
            continue
        history = list(get_attr(job, "status_history", "statusHistory", default=[]) or [])
        history.append(
            {
                "at": utcnow().isoformat(),
                "by": str(get_user_id(admin_user) or ""),
                "from": get_attr(job, "status"),
                "to": payload.status,
                "reason": payload.reason,
            }
        )
        set_attr(job, history[-100:], "status_history", "statusHistory")
        previous_status = get_attr(job, "status")
        set_attr(job, payload.status, "status")
        becomes_published = payload.status == "active" and previous_status != "active"
        if payload.status == "active" and get_attr(job, "published_at", "publishedAt") is None:
            set_attr(job, utcnow(), "published_at", "publishedAt")
        set_attr(job, utcnow(), "updated_at", "updatedAt")
        saved = save(db, job)
        if becomes_published:
            _emit_job_published(db, saved)
        updated += 1
    return BulkStatusResult(requested=len(payload.job_ids), updated=updated)


def _admin_user_to_read(user: Any) -> UserRead:
    return UserRead(
        id=str(get_user_id(user) or ""),
        email=get_primary_email(user),
        name=get_attr(user, "display_name", "name", "full_name", "username"),
        roles=get_user_roles(user),
        email_verified=is_email_verified(user),
        created_at=get_attr(user, "created_at", "createdAt"),
        deletion_requested_at=get_attr(user, "deletion_requested_at", "deletionRequestedAt"),
        deletion_scheduled_for=get_attr(user, "deletion_scheduled_for", "deletionScheduledFor"),
    )


def _search_users(db: Any, user_model: Any, q: str, limit: int = 50) -> list[Any]:
    """Indexed-ish email/name search so admins can find users to promote
    (EMP-015). Pushes ILIKE-style predicates to the DB where the model
    exposes columns; falls back to a Python scan for plain test rigs."""
    needle = q.strip().lower()
    email_field = get_model_field(user_model, "email")
    name_field = get_model_field(user_model, "display_name", "name", "username")
    if email_field is not None:
        from sqlalchemy import func, or_

        pattern = f"%{needle}%"
        predicate = func.lower(email_field).like(pattern)
        if name_field is not None:
            predicate = or_(predicate, func.lower(name_field).like(pattern))
        return query_all(db, user_model, filters=[predicate], limit=limit)
    matches = []
    for user in query_all(db, user_model):
        email = (get_primary_email(user) or "").lower()
        name = str(get_attr(user, "display_name", "name", "username", default="") or "").lower()
        if needle in email or needle in name:
            matches.append(user)
            if len(matches) >= limit:
                break
    return matches


@router.get("/users", response_model=list[UserRead])
def admin_users(
    q: str | None = Query(default=None, min_length=2, max_length=120),
    db: Any = Depends(get_db),
    admin_user: Any = Depends(require_admin),
):
    """Without ``q``: the existing admins (role-management overview).
    With ``q``: search ALL users by email/name so a user can be found and
    promoted — previously only existing admins were ever returned, making
    promotion a dead-end (EMP-015)."""
    user_model = resolve_model("User")
    if q:
        return [_admin_user_to_read(user) for user in _search_users(db, user_model, q)]
    users = [_admin_user_to_read(user) for user in query_all(db, user_model) if "admin" in get_user_roles(user)]
    return users[:100]


@router.post("/users/{user_id}/roles/{role}", response_model=UserRead)
def grant_role(user_id: str, role: str, db: Any = Depends(get_db), admin_user: Any = Depends(require_admin)):
    if role != "admin":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only the admin role can be managed")
    user = get_by_id(db, resolve_model("User"), user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    roles = set(get_user_roles(user))
    roles.add(role)
    set_attr(user, sorted(roles), "roles")
    return UserRead(
        id=str(get_user_id(save(db, user)) or ""),
        email=get_primary_email(user),
        name=get_attr(user, "display_name", "name", "full_name", "username"),
        roles=sorted(roles),
        email_verified=is_email_verified(user),
        created_at=get_attr(user, "created_at", "createdAt"),
    )


@router.delete("/users/{user_id}/roles/{role}", response_model=UserRead)
def revoke_role(user_id: str, role: str, db: Any = Depends(get_db), admin_user: Any = Depends(require_admin)):
    if role != "admin":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only the admin role can be managed")
    if user_id == get_user_id(admin_user):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot revoke your own admin role")
    user = get_by_id(db, resolve_model("User"), user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    roles = [item for item in get_user_roles(user) if item != role]
    set_attr(user, roles, "roles")
    return UserRead(
        id=str(get_user_id(save(db, user)) or ""),
        email=get_primary_email(user),
        name=get_attr(user, "display_name", "name", "full_name", "username"),
        roles=roles,
        email_verified=is_email_verified(user),
        created_at=get_attr(user, "created_at", "createdAt"),
    )


@router.get("/reports", response_model=list[ReportRead])
def admin_reports(
    resolution: str | None = Query(default=None),
    db: Any = Depends(get_db),
    admin_user: Any = Depends(require_admin),
):
    report_model = resolve_model("JobReport", "Report", "JobReports")
    if resolution and resolution not in VALID_RESOLUTIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid report resolution")
    from app.routers.reports import report_to_read

    items = _pushdown_admin_reports(db, report_model, resolution)
    return [report_to_read(item) for item in items[:200]]
