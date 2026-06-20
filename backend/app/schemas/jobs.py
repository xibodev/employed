from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class JobCreate(BaseModel):
    title: str
    company: str | None = None
    location: str | None = None
    url: str | None = None
    contact: str
    apply_whatsapp: str | None = None
    jobtype: str
    description: str
    remote: bool = False
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
    salary_currency: str | None = None
    salary_period: str | None = None
    # When set, the job is posted on behalf of this company (R4.4). The platform
    # only honours it when the caller holds the job:post permission in that
    # company; otherwise the request is rejected (R4.5). A null value keeps the
    # job as a legacy/anonymous listing (R4.3).
    company_id: str | None = None
    recaptcha_token: str | None = None


class JobUpdate(BaseModel):
    title: str | None = None
    company: str | None = None
    location: str | None = None
    url: str | None = None
    contact: str | None = None
    apply_whatsapp: str | None = None
    jobtype: str | None = None
    description: str | None = None
    remote: bool | None = None
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
    salary_currency: str | None = None
    salary_period: str | None = None


class JobRead(BaseModel):
    id: str
    slug: str | None = None
    title: str
    company: str | None = None
    country: str | None = None
    location: str | None = None
    url: str | None = None
    contact: str | None = None
    apply_whatsapp: str | None = None
    jobtype: str | None = None
    description: str | None = None
    html_description: str | None = None
    remote: bool = False
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    user_id: str | None = None
    user_name: str | None = None
    status: str | None = None
    featured_through: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    published_at: datetime | None = None
    site_url: str | None = None

    model_config = ConfigDict(from_attributes=True)


class JobListResponse(BaseModel):
    items: list[JobRead]
    total: int
    page: int
    page_size: int


class JobCountResponse(BaseModel):
    total: int
