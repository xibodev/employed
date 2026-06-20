from __future__ import annotations

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AuditLog(Base):
    """Append-only record of a privileged, verification, or moderation action (R22).

    `created_at` (from `Base`) serves as the timestamp. Rows are never updated
    or deleted; a system actor is represented by a null `actor_id` plus an
    `actor_label`.
    """

    __tablename__ = "audit_logs"

    # Append-only (R22.1/R22.3): rows are never updated, so there is no
    # `updated_at` column in migration 003. Cancel the one inherited from
    # `Base` so the ORM schema matches the table.
    updated_at = None

    actor_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
    )
    actor_label: Mapped[str | None] = mapped_column(sa.String(128))
    action: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    target_type: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    target_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    before: Mapped[dict[str, Any] | None] = mapped_column(MutableDict.as_mutable(JSONB))
    after: Mapped[dict[str, Any] | None] = mapped_column(MutableDict.as_mutable(JSONB))
