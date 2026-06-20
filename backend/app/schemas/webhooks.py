from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import WebhookEvent


class WebhookEndpointCreate(BaseModel):
    """Request body for registering an outbound webhook endpoint (R20.4).

    ``company_id`` is optional: when omitted the endpoint is platform-level and
    receives matching events across all tenants; when supplied the endpoint is
    scoped to that company. ``events`` is the set of :class:`WebhookEvent`
    values the endpoint subscribes to. The ``secret`` is used to sign delivery
    payloads and is write-only — it is never echoed back in reads.
    """

    url: str = Field(min_length=1, max_length=2048)
    secret: str = Field(min_length=1, max_length=256)
    events: list[WebhookEvent] = Field(min_length=1)
    company_id: UUID | None = None
    active: bool = True


class WebhookEndpointRead(BaseModel):
    """Endpoint view returned by the admin webhook endpoints.

    The signing ``secret`` is intentionally omitted so it is never returned over
    the wire after registration.
    """

    id: UUID
    company_id: UUID | None = None
    url: str
    events: list[WebhookEvent] = Field(default_factory=list)
    active: bool

    model_config = ConfigDict(from_attributes=True)
