from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PGUUID
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import ProfileStatus, ProfileType, VerificationState, pg_enum

if TYPE_CHECKING:
    from app.models.user import User


class Profile(Base):
    __tablename__ = "profiles"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    user_name: Mapped[str | None] = mapped_column(sa.String(128))
    custom_image_url: Mapped[str | None] = mapped_column(sa.String(2048))
    name: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    type: Mapped[ProfileType] = mapped_column(pg_enum(ProfileType, "profile_type_enum"), nullable=False)
    title: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    location: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    description: Mapped[str] = mapped_column(sa.Text, nullable=False)
    available_for_hire: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        default=False,
        server_default=sa.text("false"),
    )
    interested_in: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(ARRAY(sa.Text())),
        nullable=False,
        default=list,
        server_default=sa.text("'{}'::text[]"),
    )
    contact: Mapped[str | None] = mapped_column(sa.String(512))
    url: Mapped[str | None] = mapped_column(sa.String(2048))
    resume_url: Mapped[str | None] = mapped_column(sa.String(2048))
    github_url: Mapped[str | None] = mapped_column(sa.String(2048))
    linkedin_url: Mapped[str | None] = mapped_column(sa.String(2048))
    stackoverflow_url: Mapped[str | None] = mapped_column(sa.String(2048))
    status: Mapped[ProfileStatus] = mapped_column(
        pg_enum(ProfileStatus, "profile_status_enum"),
        nullable=False,
        default=ProfileStatus.pending,
        server_default=sa.text("'pending'"),
    )
    random_sorter: Mapped[float | None] = mapped_column(sa.Float)
    json_resume: Mapped[dict[str, Any] | None] = mapped_column(MutableDict.as_mutable(JSONB))
    verification_status: Mapped[VerificationState] = mapped_column(
        pg_enum(VerificationState, "verificationstate"),
        nullable=False,
        default=VerificationState.unverified,
        server_default=sa.text("'unverified'"),
    )
    external_refs: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSONB),
        nullable=False,
        default=dict,
        server_default=sa.text("'{}'::jsonb"),
    )

    user: Mapped[User] = relationship(back_populates="profile")
