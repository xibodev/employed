from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import MembershipStatus, TenantRole, pg_enum


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (sa.UniqueConstraint("user_id", "company_id", name="uq_memberships_user_company"),)

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[TenantRole] = mapped_column(pg_enum(TenantRole, "tenantrole"), nullable=False)
    status: Mapped[MembershipStatus] = mapped_column(pg_enum(MembershipStatus, "membershipstatus"), nullable=False)
    invited_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
    )
