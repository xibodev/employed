from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import MarketKey, PaymentProviderKey, PaymentStatus, pg_enum

# Recommended indexes for common query patterns:
# - ix_payment_intents_provider_ref(provider_ref) for webhook provider reference lookups.

if TYPE_CHECKING:
    from app.models.job import Job
    from app.models.user import User


class PaymentIntent(Base):
    __tablename__ = "payment_intents"
    # EMP-009: mirrors the indexes created in 001_initial_schema.py
    # (idx_payment_intents_provider_ref is partial there).
    __table_args__ = (
        sa.Index(
            "idx_payment_intents_provider_ref",
            "provider_ref",
            postgresql_where=sa.text("provider_ref IS NOT NULL"),
        ),
        sa.Index("idx_payment_intents_job_user", "job_id", "user_id"),
    )

    job_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    market_key: Mapped[MarketKey] = mapped_column(pg_enum(MarketKey, "market_key_enum"), nullable=False)
    provider_key: Mapped[PaymentProviderKey] = mapped_column(
        pg_enum(PaymentProviderKey, "payment_provider_key_enum"),
        nullable=False,
    )
    provider_ref: Mapped[str | None] = mapped_column(sa.String(256))
    status: Mapped[PaymentStatus] = mapped_column(
        pg_enum(PaymentStatus, "payment_status_enum"),
        nullable=False,
        default=PaymentStatus.pending,
        server_default=sa.text("'pending'"),
    )
    amount: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    currency: Mapped[str] = mapped_column(sa.String(3), nullable=False)
    payer_msisdn: Mapped[str | None] = mapped_column(sa.String(4))
    payer_msisdn_hash: Mapped[str | None] = mapped_column(sa.String(64))
    extended_through: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(sa.String(256))
    simulator: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        default=False,
        server_default=sa.text("false"),
    )
    meta: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSONB),
        nullable=False,
        default=dict,
        server_default=sa.text("'{}'::jsonb"),
    )
    settled_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))

    job: Mapped[Job] = relationship(back_populates="payment_intents")
    user: Mapped[User] = relationship(back_populates="payment_intents")

    @property
    def is_terminal(self) -> bool:
        return self.status in {
            PaymentStatus.completed,
            PaymentStatus.failed,
            PaymentStatus.cancelled,
            PaymentStatus.expired,
        }
