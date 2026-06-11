from __future__ import annotations

from datetime import datetime
import re
import unicodedata
from typing import TYPE_CHECKING, Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import Country, JobStatus, JobType, SalaryCurrency, SalaryPeriod, pg_enum

# Recommended indexes for common query patterns:
# - ix_jobs_status_country_created_at(status, country, created_at) for the primary jobs listing query.

if TYPE_CHECKING:
    from app.models.job_report import JobReport
    from app.models.payment_intent import PaymentIntent
    from app.models.user import User


class Job(Base):
    __tablename__ = "jobs"
    # EMP-009: index names/definitions mirror the ones created (partly via
    # raw SQL) in alembic/versions/001_initial_schema.py so autogenerate
    # does not propose duplicates or drops.
    __table_args__ = (
        sa.Index("idx_jobs_status_country_created", "status", "country", sa.text("created_at DESC")),
        sa.Index("idx_jobs_user_id", "user_id"),
        sa.Index(
            "idx_jobs_featured",
            "featured_through",
            postgresql_where=sa.text("featured_through IS NOT NULL"),
        ),
        sa.Index(
            "idx_jobs_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
        sa.Index(
            "idx_jobs_company_trgm",
            "company",
            postgresql_using="gin",
            postgresql_ops={"company": "gin_trgm_ops"},
        ),
    )

    user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
    )
    title: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    company: Mapped[str | None] = mapped_column(sa.String(256))
    country: Mapped[Country] = mapped_column(pg_enum(Country, "country_enum"), nullable=False)
    location: Mapped[str | None] = mapped_column(sa.String(256))
    url: Mapped[str | None] = mapped_column(sa.String(2048))
    contact: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    apply_whatsapp: Mapped[str | None] = mapped_column(sa.String(32))
    job_type: Mapped[JobType] = mapped_column(pg_enum(JobType, "job_type_enum"), nullable=False)
    remote: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        default=False,
        server_default=sa.text("false"),
    )
    description: Mapped[str] = mapped_column(sa.Text, nullable=False)
    html_description: Mapped[str | None] = mapped_column(sa.Text)
    salary_min: Mapped[int | None] = mapped_column(sa.Integer)
    salary_max: Mapped[int | None] = mapped_column(sa.Integer)
    salary_currency: Mapped[SalaryCurrency | None] = mapped_column(pg_enum(SalaryCurrency, "salary_currency_enum"))
    salary_period: Mapped[SalaryPeriod | None] = mapped_column(pg_enum(SalaryPeriod, "salary_period_enum"))
    status: Mapped[JobStatus] = mapped_column(
        pg_enum(JobStatus, "job_status_enum"),
        nullable=False,
        default=JobStatus.pending,
        server_default=sa.text("'pending'"),
    )
    featured_through: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    featured_charge_history: Mapped[list[Any]] = mapped_column(
        MutableList.as_mutable(JSONB),
        nullable=False,
        default=list,
        server_default=sa.text("'[]'::jsonb"),
    )
    status_history: Mapped[list[dict[str, Any]]] = mapped_column(
        MutableList.as_mutable(JSONB),
        nullable=False,
        default=list,
        server_default=sa.text("'[]'::jsonb"),
    )
    published_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    expired_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    recaptcha_score: Mapped[float | None] = mapped_column(sa.Float)

    user: Mapped[User | None] = relationship(back_populates="jobs")
    payment_intents: Mapped[list[PaymentIntent]] = relationship(
        back_populates="job",
        passive_deletes=True,
    )
    reports: Mapped[list[JobReport]] = relationship(
        back_populates="job",
        passive_deletes=True,
    )

    @property
    def slug(self) -> str:
        normalized = unicodedata.normalize("NFKD", self.title).encode("ascii", "ignore").decode("ascii")
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized.lower()).strip("-")
        return slug or "job"

    @property
    def featured_allowed(self) -> bool:
        return self.status in {JobStatus.pending, JobStatus.active}
