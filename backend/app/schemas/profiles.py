from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProfileCreate(BaseModel):
    name: str
    type: str
    title: str
    location: str
    description: str
    available_for_hire: bool = False
    interested_in: list[str] = Field(default_factory=list)
    contact: str | None = None
    url: str | None = None
    resume_url: str | None = None
    github_url: str | None = None
    linkedin_url: str | None = None
    stackoverflow_url: str | None = None
    custom_image_url: str | None = None


class ProfileUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    title: str | None = None
    location: str | None = None
    description: str | None = None
    available_for_hire: bool | None = None
    interested_in: list[str] | None = None
    contact: str | None = None
    url: str | None = None
    resume_url: str | None = None
    github_url: str | None = None
    linkedin_url: str | None = None
    stackoverflow_url: str | None = None
    custom_image_url: str | None = None


class ProfileRead(BaseModel):
    id: str
    user_id: str | None = None
    user_name: str | None = None
    name: str | None = None
    type: str | None = None
    title: str | None = None
    location: str | None = None
    description: str | None = None
    html_description: str | None = None
    available_for_hire: bool = False
    interested_in: list[str] = Field(default_factory=list)
    contact: str | None = None
    url: str | None = None
    resume_url: str | None = None
    github_url: str | None = None
    linkedin_url: str | None = None
    stackoverflow_url: str | None = None
    custom_image_url: str | None = None
    status: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ProfileVersionSaveRequest(BaseModel):
    """Request body for saving a profile version (R13.2).

    When ``json_resume`` is supplied it updates the live profile's working copy
    before the immutable snapshot is taken; otherwise the current working copy is
    snapshotted as-is.
    """

    json_resume: dict[str, Any] | None = None


class ProfileVersionSummary(BaseModel):
    """Lightweight view of an immutable profile version (R13.2/13.3)."""

    id: UUID
    version_number: int
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ProfileVersionRead(ProfileVersionSummary):
    """Full profile-version view including the immutable JSON Resume snapshot."""

    json_resume: dict[str, Any] = Field(default_factory=dict)
