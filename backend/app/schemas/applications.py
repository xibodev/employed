from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ApplicationStatus


class ApplicationRead(BaseModel):
    """Application view returned by the recruiter list and status-change endpoints."""

    id: UUID
    job_id: UUID
    company_id: UUID | None = None
    candidate_user_id: UUID | None = None
    candidate_snapshot: dict[str, Any] | None = None
    status: ApplicationStatus
    resume_version_id: UUID | None = None
    cover_note: str | None = None
    source: str

    model_config = ConfigDict(from_attributes=True)


class ApplicationStatusChangeRequest(BaseModel):
    """Request body for advancing an Application to a new pipeline stage (R17.3).

    Only the target ``new_status`` is supplied; the owning company and the acting
    recruiter are resolved server-side from the application and the authenticated
    request, never accepted from the client.
    """

    new_status: ApplicationStatus


class ApplicationCreateRequest(BaseModel):
    """Request body for creating a tracked Application (R16.2).

    Exactly one candidate reference must be supplied: either a platform
    ``candidate_user_id`` or an inline ``candidate_snapshot``. The application is
    always created at the first pipeline stage (``applied``), so status is not
    part of the request.
    """

    job_id: UUID
    candidate_user_id: UUID | None = None
    candidate_snapshot: dict[str, Any] | None = None
    company_id: UUID | None = None
    resume_version_id: UUID | None = None
    cover_note: str | None = None
    source: str = Field(default="platform", max_length=64)
