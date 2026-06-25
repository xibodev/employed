"""Property-based test for "exactly one live profile per user" (Property 12).

The production ``Profile`` / ``ProfileVersion`` models use Postgres-only types
(``PGUUID`` with a ``gen_random_uuid()`` server default, ``JSONB``, ``ARRAY`` and
native enums), and :func:`app.services.profiles_versioning.ensure_live_profile`
relies on server-side id generation. Those cannot be materialised on SQLite, so
this test mirrors the convention used by ``test_rbac_properties.py``: it defines
SQLite-friendly stand-in models that carry exactly the columns the service reads
and writes -- including the ``unique=True`` constraint on ``Profile.user_id``
that enforces the single-live-profile invariant -- and points the service module
at them. The real ``ensure_live_profile`` / ``save_version`` / ``get_live_profile``
query code paths therefore execute for real against an in-memory database.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
import sqlalchemy as sa
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import create_engine
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.enums import ProfileType
from app.services import profiles_versioning as pv
from app.services.profiles_versioning import ensure_live_profile, get_live_profile, save_version


class _Base(DeclarativeBase):
    pass


class _Profile(_Base):
    """SQLite-friendly stand-in for ``app.models.profile.Profile``.

    Only the columns the versioning service touches are modelled. ``user_id`` is
    ``unique`` -- the database-level guarantee behind Property 12 -- and ``id``
    has a Python-side default so ``ensure_live_profile`` (which does not pass an
    id) can materialise rows without the production ``gen_random_uuid()`` server
    default.
    """

    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(sa.String(36), unique=True, nullable=False, index=True)
    user_name: Mapped[str | None] = mapped_column(sa.String(128))
    custom_image_url: Mapped[str | None] = mapped_column(sa.String(2048))
    name: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    type: Mapped[ProfileType] = mapped_column(sa.Enum(ProfileType, native_enum=False), nullable=False)
    title: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    location: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    description: Mapped[str] = mapped_column(sa.Text, nullable=False)
    available_for_hire: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    interested_in: Mapped[list[str] | None] = mapped_column(sa.JSON)
    contact: Mapped[str | None] = mapped_column(sa.String(512))
    url: Mapped[str | None] = mapped_column(sa.String(2048))
    resume_url: Mapped[str | None] = mapped_column(sa.String(2048))
    github_url: Mapped[str | None] = mapped_column(sa.String(2048))
    linkedin_url: Mapped[str | None] = mapped_column(sa.String(2048))
    stackoverflow_url: Mapped[str | None] = mapped_column(sa.String(2048))
    json_resume: Mapped[dict[str, Any] | None] = mapped_column(MutableDict.as_mutable(sa.JSON))


class _ProfileVersion(_Base):
    """SQLite-friendly stand-in for ``app.models.profile_version.ProfileVersion``."""

    __tablename__ = "profile_versions"
    __table_args__ = (sa.UniqueConstraint("profile_id", "version_number", name="uq_profile_versions_profile_version"),)

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=lambda: str(uuid4()))
    profile_id: Mapped[str] = mapped_column(sa.String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(sa.String(36), nullable=False)
    version_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    json_resume: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(sa.JSON), nullable=False)


@pytest.fixture(autouse=True)
def _patch_models(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the versioning service at the SQLite-friendly stand-in models."""
    monkeypatch.setattr(pv, "Profile", _Profile)
    monkeypatch.setattr(pv, "ProfileVersion", _ProfileVersion)


def _build_session() -> tuple[Session, sa.Engine]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    _Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    return session_factory(), engine


# Printable-ASCII text keeps generated values clear of surrogate/encoding edge
# cases that have nothing to do with the property under test.
_text = st.text(alphabet=st.characters(min_codepoint=32, max_codepoint=126), max_size=24)


@st.composite
def _action_sequence(draw: st.DrawFn) -> tuple[list[str], list[dict[str, Any]]]:
    """A pool of users plus a sequence of profile-save / version-capture actions.

    Each action targets one of the users and is either a plain profile save
    (materialise the live profile / re-save it) or a version capture (save plus
    an immutable snapshot). Actions repeat freely across users so the sequence
    exercises many interleavings of saves and captures.
    """

    user_count = draw(st.integers(min_value=1, max_value=3))
    user_ids = [str(uuid4()) for _ in range(user_count)]
    actions = draw(
        st.lists(
            st.fixed_dictionaries(
                {
                    "user_index": st.integers(min_value=0, max_value=user_count - 1),
                    "capture_version": st.booleans(),
                    "name": _text,
                    "title": _text,
                    "resume_name": _text,
                }
            ),
            min_size=1,
            max_size=20,
        )
    )
    return user_ids, actions


# Feature: multi-tenant-hiring-platform, Property 12: Exactly one live profile per user
@settings(max_examples=100, deadline=None)
@given(scenario=_action_sequence())
def test_exactly_one_live_profile_per_user(scenario: tuple[list[str], list[dict[str, Any]]]) -> None:
    """For any sequence of profile saves and version captures by a user, that
    user always has exactly one live profile.

    Validates: Requirements 13.1
    """

    user_ids, actions = scenario
    db, engine = _build_session()
    try:
        touched: set[str] = set()
        for action in actions:
            user_id = user_ids[action["user_index"]]
            touched.add(user_id)

            defaults = {"name": action["name"], "title": action["title"]}
            profile = ensure_live_profile(db, user_id=user_id, defaults=defaults)
            if action["capture_version"]:
                save_version(db, profile=profile, json_resume={"basics": {"name": action["resume_name"]}})
            db.commit()

            # The invariant must hold after every single action, not just at the
            # end: re-saving / re-capturing never spawns a second live profile.
            assert db.query(_Profile).filter(_Profile.user_id == user_id).count() == 1
            live = get_live_profile(db, user_id)
            assert live is not None
            assert str(live.user_id) == user_id

        # Every user that was ever saved ends with exactly one live profile, and
        # no live profile exists for a user that was never touched.
        for user_id in touched:
            assert db.query(_Profile).filter(_Profile.user_id == user_id).count() == 1
            assert get_live_profile(db, user_id) is not None
        for user_id in set(user_ids) - touched:
            assert get_live_profile(db, user_id) is None
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":  # pragma: no cover - convenience for ad-hoc runs
    pytest.main([__file__, "-v"])
