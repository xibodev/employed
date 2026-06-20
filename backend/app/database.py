from __future__ import annotations

from datetime import datetime, timezone
from typing import Generator
from uuid import UUID

from sqlalchemy import MetaData, create_engine, event, func, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.types import DateTime
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.config import settings


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    __abstract__ = True
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


@event.listens_for(Base, "before_insert", propagate=True)
def set_created_and_updated_timestamps(_mapper, _connection, target: Base) -> None:
    now = datetime.now(timezone.utc)
    if getattr(target, "created_at", None) is None:
        target.created_at = now
    # Append-only models (e.g. ProfileVersion, AuditLog) cancel the inherited
    # `updated_at` column; only set it when the model actually maps it.
    if "updated_at" in type(target).__table__.columns:
        target.updated_at = now


@event.listens_for(Base, "before_update", propagate=True)
def set_updated_timestamp(_mapper, _connection, target: Base) -> None:
    if "updated_at" in type(target).__table__.columns:
        target.updated_at = datetime.now(timezone.utc)


def _engine_options() -> dict[str, object]:
    options: dict[str, object] = {
        "future": True,
        "pool_pre_ping": True,
    }
    url = make_url(settings.sync_database_url)
    if not url.drivername.startswith("sqlite"):
        options.update(
            {
                "pool_size": settings.database_pool_size,
                "max_overflow": settings.database_max_overflow,
                "pool_timeout": settings.database_pool_timeout,
                "pool_recycle": settings.database_pool_recycle,
            }
        )
    return options


engine: Engine = create_engine(settings.sync_database_url, **_engine_options())

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
