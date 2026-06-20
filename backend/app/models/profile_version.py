from __future__ import annotations

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProfileVersion(Base):
    """Immutable, append-only snapshot of a profile's JSON Resume (R13).

    A new version is written each time a profile is saved; rows are never
    mutated. `version_number` is monotonic per profile and unique within it.
    """

    __tablename__ = "profile_versions"
    __table_args__ = (sa.UniqueConstraint("profile_id", "version_number", name="uq_profile_versions_profile_version"),)

    # Append-only/immutable (R13.3/R13.4): rows are never mutated, so there is
    # no `updated_at` column in migration 003. Cancel the one inherited from
    # `Base` so the ORM schema matches the table.
    updated_at = None

    profile_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    json_resume: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSONB),
        nullable=False,
    )
