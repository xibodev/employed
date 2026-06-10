from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import get_optional_current_user, require_admin, get_user_id
from app.database import get_db
from app.schemas.reports import ReportCreate, ReportRead, ReportResolve
from app.services.model_utils import get_attr, get_by_id, resolve_model, save, set_attr, utcnow

router = APIRouter(prefix="/reports", tags=["reports"])

VALID_REASONS = {"spam", "scam", "discriminatory", "wrong_country", "expired_or_filled", "duplicate"}
VALID_RESOLUTIONS = {"reviewed", "dismissed", "job_removed"}


def _report_model():
    return resolve_model("JobReport", "Report", "JobReports")


def _job_model():
    return resolve_model("Job", "Jobs")


def report_to_read(report: Any) -> ReportRead:
    """Serialize a JobReport row to ReportRead.

    All id-like fields are wrapped in str() because the Postgres model maps
    them as uuid.UUID, while ReportRead declares plain str (EMP-026a).
    """
    return ReportRead(
        id=str(get_attr(report, "id", "_id", default="")),
        job_id=str(get_attr(report, "job_id", "jobId", default="")),
        reason=get_attr(report, "reason", default=""),
        details=get_attr(report, "details"),
        reporter_user_id=(
            str(reporter_user_id)
            if (reporter_user_id := get_attr(report, "reporter_user_id", "reporterUserId")) is not None
            else None
        ),
        resolution=get_attr(report, "resolution"),
        resolved_by=(
            str(resolved_by) if (resolved_by := get_attr(report, "resolved_by", "resolvedBy")) is not None else None
        ),
        resolved_at=get_attr(report, "resolved_at", "resolvedAt"),
        created_at=get_attr(report, "created_at", "createdAt"),
    )


@router.post("", response_model=ReportRead, status_code=status.HTTP_201_CREATED)
def create_report(
    payload: ReportCreate,
    db: Any = Depends(get_db),
    current_user: Any | None = Depends(get_optional_current_user),
):
    if payload.reason not in VALID_REASONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid report reason")
    if get_by_id(db, _job_model(), payload.job_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    report = _report_model()()
    set_attr(report, payload.job_id, "job_id", "jobId")
    set_attr(report, payload.reason, "reason")
    set_attr(report, payload.details, "details")
    set_attr(report, get_user_id(current_user) if current_user else None, "reporter_user_id", "reporterUserId")
    set_attr(report, "pending", "resolution")
    set_attr(report, utcnow(), "created_at", "createdAt")
    return report_to_read(save(db, report))


@router.patch("/{report_id}/resolve", response_model=ReportRead)
def resolve_report(
    report_id: str,
    payload: ReportResolve,
    db: Any = Depends(get_db),
    admin_user: Any = Depends(require_admin),
):
    if payload.resolution not in VALID_RESOLUTIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid report resolution")
    report = get_by_id(db, _report_model(), report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    set_attr(report, payload.resolution, "resolution")
    set_attr(report, get_user_id(admin_user), "resolved_by", "resolvedBy")
    set_attr(report, utcnow(), "resolved_at", "resolvedAt")
    return report_to_read(save(db, report))
