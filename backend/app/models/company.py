from __future__ import annotations

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import MarketKey, VerificationState, pg_enum


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (sa.UniqueConstraint("market", "slug", name="uq_companies_market_slug"),)

    name: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    slug: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    market: Mapped[MarketKey] = mapped_column(pg_enum(MarketKey, "market_key_enum"), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text)
    logo_url: Mapped[str | None] = mapped_column(sa.String(2048))
    website: Mapped[str | None] = mapped_column(sa.String(2048))
    verification_status: Mapped[VerificationState] = mapped_column(
        pg_enum(VerificationState, "verificationstate"),
        nullable=False,
        default=VerificationState.unverified,
        server_default=sa.text("'unverified'"),
    )
    created_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
    )
    verified_email_domains: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSONB),
        nullable=False,
        default=list,
        server_default=sa.text("'[]'::jsonb"),
    )
    trust_badges: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSONB),
        nullable=False,
        default=list,
        server_default=sa.text("'[]'::jsonb"),
    )
    external_refs: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSONB),
        nullable=False,
        default=dict,
        server_default=sa.text("'{}'::jsonb"),
    )
