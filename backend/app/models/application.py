from __future__ import annotations

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import ApplicationStatus, pg_enum


class Application(Base):
    """A tracked job application carrying exactly one candidate reference (R16).

    The candidate is identified either by `candidate_user_id` (a platform user)
    or by an inline `candidate_snapshot`; a check constraint requires at least
    one of the two to be present.
    """

    __tablename__ = "applications"
    __table_args__ = (
        sa.CheckConstraint(
            "candidate_user_id IS NOT NULL OR candidate_snapshot IS NOT NULL",
            name="candidate_present",
        ),
    )

    job_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    candidate_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
    )
    candidate_snapshot: Mapped[dict[str, Any] | None] = mapped_column(MutableDict.as_mutable(JSONB))
    company_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="SET NULL"),
    )
    status: Mapped[ApplicationStatus] = mapped_column(
        pg_enum(ApplicationStatus, "applicationstatus"),
        nullable=False,
        default=ApplicationStatus.applied,
        server_default=sa.text("'applied'"),
    )
    resume_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("profile_versions.id", ondelete="SET NULL"),
    )
    cover_note: Mapped[str | None] = mapped_column(sa.Text)
    source: Mapped[str] = mapped_column(
        sa.String(64),
        nullable=False,
        default="platform",
        server_default=sa.text("'platform'"),
    )
    external_refs: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSONB),
        nullable=False,
        default=dict,
        server_default=sa.text("'{}'::jsonb"),
    )
