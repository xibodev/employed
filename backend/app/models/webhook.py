from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import WebhookEvent, pg_enum


class WebhookEndpoint(Base):
    """A registered receiver for domain events (R20).

    `company_id` is nullable so platform-level endpoints can subscribe without
    being scoped to a tenant. `events` is the set of `WebhookEvent` values the
    endpoint is subscribed to.
    """

    __tablename__ = "webhook_endpoints"

    company_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="CASCADE"),
    )
    url: Mapped[str] = mapped_column(sa.String(2048), nullable=False)
    secret: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    events: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSONB),
        nullable=False,
        default=list,
        server_default=sa.text("'[]'::jsonb"),
    )
    active: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        default=True,
        server_default=sa.text("true"),
    )


class WebhookDelivery(Base):
    """A single delivery attempt record for an emitted event (R20).

    Deliveries start `pending` and are retried with bounded exponential backoff
    (`next_attempt_at`), transitioning to `delivered` or `failed` (R20.5).
    """

    __tablename__ = "webhook_deliveries"

    endpoint_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("webhook_endpoints.id", ondelete="CASCADE"),
        nullable=False,
    )
    event: Mapped[WebhookEvent] = mapped_column(pg_enum(WebhookEvent, "webhookevent"), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSONB),
        nullable=False,
        default=dict,
        server_default=sa.text("'{}'::jsonb"),
    )
    status: Mapped[str] = mapped_column(
        sa.String(32),
        nullable=False,
        default="pending",
        server_default=sa.text("'pending'"),
    )
    attempts: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        default=0,
        server_default=sa.text("0"),
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(sa.Text)
