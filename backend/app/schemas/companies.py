from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import MarketKey, VerificationState


class CompanyCreate(BaseModel):
    """Request body for creating a Company (R1.1).

    The owning ``market`` is resolved per-request from the hostname by
    ``MarketMiddleware`` (mirroring how a Job derives its country/market) and is
    never accepted from the client — market and tenant are orthogonal axes
    (R1.6). Managed fields (slug, verification_status, created_by) are set by the
    service and are not part of the request.
    """

    name: str = Field(min_length=1, max_length=256)
    description: str | None = None
    logo_url: str | None = Field(default=None, max_length=2048)
    website: str | None = Field(default=None, max_length=2048)


class CompanyRead(BaseModel):
    """Company view returned by the read/create/verify endpoints."""

    id: UUID
    name: str
    slug: str
    market: MarketKey
    description: str | None = None
    logo_url: str | None = None
    website: str | None = None
    verification_status: VerificationState
    verified_email_domains: list[str] = Field(default_factory=list)
    trust_badges: list[str] = Field(default_factory=list)
    created_by: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class DomainVerifyRequest(BaseModel):
    """Request body for company domain verification (R9.1/9.2).

    ``method`` selects the proof: ``dns`` checks for ``expected_token`` in the
    domain's DNS TXT records (R9.1); ``member_email`` checks for an active member
    with a verified email on the claimed domain (R9.2). When ``method`` is
    omitted it is inferred: ``dns`` if ``expected_token`` is supplied, otherwise
    ``member_email``.
    """

    domain: str = Field(min_length=1)
    method: Literal["dns", "member_email"] | None = None
    expected_token: str | None = None
