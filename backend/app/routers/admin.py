from __future__ import annotations

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

router = APIRouter(prefix="/admin", tags=["admin"])

VALID_STATUSES = {"pending", "active", "flagged", "inactive", "filled"}
VALID_RESOLUTIONS = {"pending", "reviewed", "dismissed", "job_removed"}


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
    set_attr(job, payload.status, "status")
    set_attr(job, history, "status_history", "statusHistory")
    if payload.status == "active" and get_attr(job, "published_at", "publishedAt") is None:
        set_attr(job, utcnow(), "published_at", "publishedAt")
    set_attr(job, utcnow(), "updated_at", "updatedAt")
    return {"job_id": job_id, "status": get_attr(save(db, job), "status")}


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
        set_attr(job, payload.status, "status")
        set_attr(job, utcnow(), "updated_at", "updatedAt")
        save(db, job)
        updated += 1
    return BulkStatusResult(requested=len(payload.job_ids), updated=updated)


@router.get("/users", response_model=list[UserRead])
def admin_users(db: Any = Depends(get_db), admin_user: Any = Depends(require_admin)):
    user_model = resolve_model("User")
    users = []
    for user in query_all(db, user_model):
        if "admin" in get_user_roles(user):
            users.append(
                UserRead(
                    id=str(get_user_id(user) or ""),
                    email=get_primary_email(user),
                    name=get_attr(user, "display_name", "name", "full_name", "username"),
                    roles=get_user_roles(user),
                    email_verified=is_email_verified(user),
                    created_at=get_attr(user, "created_at", "createdAt"),
                    deletion_requested_at=get_attr(user, "deletion_requested_at", "deletionRequestedAt"),
                    deletion_scheduled_for=get_attr(user, "deletion_scheduled_for", "deletionScheduledFor"),
                )
            )
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
