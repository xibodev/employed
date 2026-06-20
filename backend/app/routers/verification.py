"""Publication moderation and verification endpoints (R11, DD-4/9).

Platform moderators (and super admins) drive marketplace trust through two kinds
of action:

* **Publication moderation** — ``block`` and ``unpublish`` change a Job's
  publication ``status`` to a non-``active`` state so the listing leaves public
  visibility (R11.1/11.2). The public ``/jobs`` list and detail queries already
  restrict to ``status == "active"``, so a blocked/unpublished job is never
  returned (Property 24). Each action writes its own ``AuditLog`` row via
  :func:`app.services.audit.write_audit` (R11.7).
* **Verification transitions** — ``mark_review`` (→ ``flagged``) and the three
  ``verify`` actions (→ ``verified``) for a Job publication, a Company, and a
  Profile run through the shared state machine in
  :func:`app.services.verification.transition`, which validates the transition,
  reconciles trust badges, and writes exactly one audit row per call (R11.3-11.7).
  An illegal transition is mapped to ``409`` and changes nothing.

Every endpoint is guarded by the matching platform permission via
:func:`app.services.rbac.require_permission`; the target resource id is resolved
from the path.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.company import Company
from app.models.enums import JobStatus, VerificationState
from app.models.job import Job
from app.models.profile import Profile
from app.models.user import User
from app.schemas.verification import (
    EntityVerificationResponse,
    JobModerationResponse,
    ModerationActionRequest,
)
from app.services.audit import write_audit
from app.services.rbac import (
    COMPANY_VERIFY,
    JOB_BLOCK,
    JOB_MARK_REVIEW,
    JOB_UNPUBLISH,
    JOB_VERIFY,
    PROFILE_VERIFY,
    require_permission,
)
from app.services.verification import IllegalTransitionError, transition

router = APIRouter(prefix="/moderation", tags=["moderation"])

ILLEGAL_TRANSITION_STATUS = status.HTTP_409_CONFLICT


def _load_job(db: Session, job_id: UUID) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


def _load_company(db: Session, company_id: UUID) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company


def _load_profile(db: Session, profile_id: UUID) -> Profile:
    profile = db.get(Profile, profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return profile


def _job_response(job: Job) -> JobModerationResponse:
    return JobModerationResponse(
        id=str(job.id),
        status=job.status.value,
        verification_status=job.verification_status.value,
    )


def _entity_response(entity: Any) -> EntityVerificationResponse:
    return EntityVerificationResponse(
        id=str(entity.id),
        verification_status=entity.verification_status.value,
    )


def _set_publication_status(
    db: Session,
    *,
    job: Job,
    new_status: JobStatus,
    actor: User,
    action: str,
    reason: str | None,
) -> JobModerationResponse:
    """Change a Job's publication status and write a moderation audit row.

    Block/unpublish move the listing out of the publicly visible ``active``
    state; the public listing/detail queries filter ``status == "active"`` so the
    job is no longer returned (R11.1/11.2, Property 24). A dedicated ``AuditLog``
    row is written for the action (R11.7).
    """
    before = job.status
    job.status = new_status

    after: dict[str, Any] = {"status": new_status.value}
    if reason is not None:
        after["reason"] = reason

    write_audit(
        db,
        actor=actor,
        action=action,
        target_type=Job.__name__,
        target_id=job.id,
        before={"status": before.value},
        after=after,
    )
    db.commit()
    db.refresh(job)
    return _job_response(job)


def _verify_entity(
    db: Session,
    *,
    entity: Any,
    target_state: VerificationState,
    actor: User,
    reason: str | None,
) -> None:
    """Drive a verifiable entity through the state machine, mapping 409 errors.

    The transition validates reachability, reconciles trust badges, and writes a
    single audit row; an illegal transition leaves the entity unchanged and is
    surfaced as ``409`` (R7 error path, R11.3-11.7).
    """
    try:
        transition(db, entity=entity, target_state=target_state, actor=actor, reason=reason)
    except IllegalTransitionError as exc:
        db.rollback()
        raise HTTPException(status_code=ILLEGAL_TRANSITION_STATUS, detail=str(exc)) from exc
    db.commit()
    db.refresh(entity)


@router.post("/jobs/{job_id}/block", response_model=JobModerationResponse)
def block_job(
    job_id: UUID,
    payload: ModerationActionRequest | None = None,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(JOB_BLOCK)),
) -> JobModerationResponse:
    """Block a publication so it is no longer publicly visible (R11.1).

    Guarded by ``job:block``; sets the job's publication status to ``flagged``
    (a non-``active`` state) so the public listing/detail queries exclude it, and
    records a ``job.block`` audit entry.
    """
    job = _load_job(db, job_id)
    reason = payload.reason if payload is not None else None
    return _set_publication_status(
        db,
        job=job,
        new_status=JobStatus.flagged,
        actor=actor,
        action="job.block",
        reason=reason,
    )


@router.post("/jobs/{job_id}/unpublish", response_model=JobModerationResponse)
def unpublish_job(
    job_id: UUID,
    payload: ModerationActionRequest | None = None,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(JOB_UNPUBLISH)),
) -> JobModerationResponse:
    """Stop a publication, removing it from public visibility (R11.2).

    Guarded by ``job:unpublish``; sets the job's publication status to
    ``inactive`` (a non-``active`` state) so the public listing/detail queries
    exclude it, and records a ``job.unpublish`` audit entry.
    """
    job = _load_job(db, job_id)
    reason = payload.reason if payload is not None else None
    return _set_publication_status(
        db,
        job=job,
        new_status=JobStatus.inactive,
        actor=actor,
        action="job.unpublish",
        reason=reason,
    )


@router.post("/jobs/{job_id}/mark-review", response_model=JobModerationResponse)
def mark_job_under_review(
    job_id: UUID,
    payload: ModerationActionRequest | None = None,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(JOB_MARK_REVIEW)),
) -> JobModerationResponse:
    """Mark a publication under review, flagging its verification state (R11.3).

    Guarded by ``job:mark_review``; transitions the job's ``verification_status``
    to ``flagged`` through the state machine, which writes the audit row.
    """
    job = _load_job(db, job_id)
    reason = payload.reason if payload is not None else None
    _verify_entity(
        db,
        entity=job,
        target_state=VerificationState.flagged,
        actor=actor,
        reason=reason,
    )
    return _job_response(job)


@router.post("/jobs/{job_id}/verify", response_model=JobModerationResponse)
def verify_job(
    job_id: UUID,
    payload: ModerationActionRequest | None = None,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(JOB_VERIFY)),
) -> JobModerationResponse:
    """Verify a publication, setting its verification state to ``verified`` (R11.4).

    Guarded by ``job:verify``; transitions the job's ``verification_status`` to
    ``verified`` through the state machine, which writes the audit row.
    """
    job = _load_job(db, job_id)
    reason = payload.reason if payload is not None else None
    _verify_entity(
        db,
        entity=job,
        target_state=VerificationState.verified,
        actor=actor,
        reason=reason,
    )
    return _job_response(job)


@router.post("/companies/{company_id}/verify", response_model=EntityVerificationResponse)
def verify_company(
    company_id: UUID,
    payload: ModerationActionRequest | None = None,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(COMPANY_VERIFY)),
) -> EntityVerificationResponse:
    """Verify a Company, setting its verification state to ``verified`` (R11.5).

    Guarded by ``company:verify``; transitions the company's
    ``verification_status`` to ``verified`` through the state machine.
    """
    company = _load_company(db, company_id)
    reason = payload.reason if payload is not None else None
    _verify_entity(
        db,
        entity=company,
        target_state=VerificationState.verified,
        actor=actor,
        reason=reason,
    )
    return _entity_response(company)


@router.post("/profiles/{profile_id}/verify", response_model=EntityVerificationResponse)
def verify_profile(
    profile_id: UUID,
    payload: ModerationActionRequest | None = None,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PROFILE_VERIFY)),
) -> EntityVerificationResponse:
    """Verify a Profile, setting its verification state to ``verified`` (R11.6).

    Guarded by ``profile:verify``; transitions the profile's
    ``verification_status`` to ``verified`` through the state machine.
    """
    profile = _load_profile(db, profile_id)
    reason = payload.reason if payload is not None else None
    _verify_entity(
        db,
        entity=profile,
        target_state=VerificationState.verified,
        actor=actor,
        reason=reason,
    )
    return _entity_response(profile)
