"""Versioned, read-only Export API (R21).

Exposes major platform entities in open interchange schemas so integrators can
extract data reliably into a full ATS without migrations:

- candidates → JSON Resume (R21.2),
- jobs → schema.org ``JobPosting`` JSON-LD,
- applications → normalized Application object.

The API version is carried in the path (``/export/v1``) rather than a header or
query parameter (R21.3), and a request for a nonexistent identifier returns
``404`` (R21.4). Route nouns (``candidates``, ``positions``, ``applications``)
follow HR Open Standards terminology where feasible (R21.5): HR Open models an
open role as a *PositionOpening*, so the job export is reachable under
``/positions`` (with a ``/jobs`` alias for schema.org/JobPosting parity).

All rendering is delegated to the side-effect-free mappers in
``app/services/export.py``; this router only loads entities and maps them.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.application import Application
from app.models.job import Job
from app.models.profile import Profile
from app.models.profile_version import ProfileVersion
from app.schemas.export import ExportDocument
from app.services.export import (
    to_job_posting_jsonld,
    to_json_resume,
    to_normalized_application,
)

# Version segment lives in the path (R21.3). Bump to /export/v2 for breaking
# changes rather than mutating these v1 contracts. Every export route is
# read-only and guarded by authentication at the router level (R21): an
# integrator must present a valid bearer token to extract any record.
router = APIRouter(prefix="/export/v1", tags=["export"], dependencies=[Depends(get_current_user)])


@router.get(
    "/candidates/{identifier}",
    response_model=ExportDocument,
    summary="Export a candidate as a JSON Resume document",
)
def export_candidate(identifier: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Return the candidate's JSON Resume by identifier (R21.2).

    The identifier resolves either a live ``Profile`` or an immutable
    ``ProfileVersion`` (both carry the canonical JSON Resume), so a stored
    snapshot can be exported by its own id. A nonexistent identifier yields
    ``404`` (R21.4).
    """
    candidate: Profile | ProfileVersion | None = db.get(Profile, identifier)
    if candidate is None:
        candidate = db.get(ProfileVersion, identifier)
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return to_json_resume(candidate)


@router.get(
    "/positions/{identifier}",
    response_model=ExportDocument,
    summary="Export a job as a schema.org JobPosting JSON-LD document",
)
@router.get(
    "/jobs/{identifier}",
    response_model=ExportDocument,
    include_in_schema=False,
)
def export_position(identifier: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Return the job as schema.org ``JobPosting`` JSON-LD by identifier.

    HR Open Standards names an open role a *PositionOpening*, so the canonical
    path is ``/positions``; ``/jobs`` is kept as an alias for schema.org
    ``JobPosting`` parity. A nonexistent identifier yields ``404`` (R21.4).
    """
    job = db.get(Job, identifier)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return to_job_posting_jsonld(job)


@router.get(
    "/applications/{identifier}",
    response_model=ExportDocument,
    summary="Export an application as a normalized Application object",
)
def export_application(identifier: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Return the normalized Application object by identifier.

    A nonexistent identifier yields ``404`` (R21.4).
    """
    application = db.get(Application, identifier)
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    return to_normalized_application(application)
