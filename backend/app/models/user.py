from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.job import Job
    from app.models.job_report import JobReport
    from app.models.payment_intent import PaymentIntent
    from app.models.profile import Profile


class User(Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(sa.String(320), unique=True, nullable=False)
    email_verified: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        default=False,
        server_default=sa.text("false"),
    )
    username: Mapped[str | None] = mapped_column(sa.String(64), unique=True)
    password_hash: Mapped[str | None] = mapped_column(sa.String(128))
    display_name: Mapped[str | None] = mapped_column(sa.String(128))
    roles: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(ARRAY(sa.Text())),
        nullable=False,
        default=list,
        server_default=sa.text("'{}'::text[]"),
    )
    oauth_providers: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSONB),
        nullable=False,
        default=dict,
        server_default=sa.text("'{}'::jsonb"),
    )
    external_refs: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSONB),
        nullable=False,
        default=dict,
        server_default=sa.text("'{}'::jsonb"),
    )
    is_developer: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        default=False,
        server_default=sa.text("false"),
    )
    deletion_requested_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    deletion_scheduled_for: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    password_changed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))

    jobs: Mapped[list[Job]] = relationship(back_populates="user", passive_deletes=True)
    profile: Mapped[Profile | None] = relationship(
        back_populates="user",
        uselist=False,
        passive_deletes=True,
    )
    payment_intents: Mapped[list[PaymentIntent]] = relationship(
        back_populates="user",
        passive_deletes=True,
    )
    reported_job_reports: Mapped[list[JobReport]] = relationship(
        back_populates="reporter_user",
        foreign_keys="JobReport.reporter_user_id",
        passive_deletes=True,
    )
    resolved_job_reports: Mapped[list[JobReport]] = relationship(
        back_populates="resolver_user",
        foreign_keys="JobReport.resolved_by",
        passive_deletes=True,
    )
