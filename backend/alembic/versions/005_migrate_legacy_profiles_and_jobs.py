"""Migrate legacy company profiles and job status history into the RBAC model.

Data migration (no schema changes). Three conversions, all reversible (R23.5):

1. Each ``Profile`` whose ``type`` is the legacy ``company`` value becomes a
   ``Company`` row owned by the profile's user, plus an ``org_owner``/``active``
   ``Membership`` linking that user to the new company (R23.1, R23.2). Created
   companies are tagged via ``external_refs.migrated_from_profile`` so the
   downgrade can identify and remove exactly the rows this migration created.

2. Jobs with a null ``company_id`` are left untouched and remain anonymous /
   legacy jobs (R23.3); the migration never deletes jobs, profiles, or users so
   all production data is preserved (R23.4).

3. Each entry in a job's ``status_history`` JSONB array is backfilled into the
   append-only ``audit_logs`` trail in order (R22.4). Backfilled rows carry a
   marker in their ``after`` payload (``after._migration``) so the downgrade can
   delete exactly them.

Revision ID: 005_legacy_profiles_jobs
Revises: 004_migrate_admins
Create Date: 2026-05-24 03:00:00
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
# NB: keep revision ids <= 32 chars — alembic_version.version_num is
# varchar(32) (created by revision 001), so a longer id overflows it.
revision = "005_legacy_profiles_jobs"
down_revision = "004_migrate_admins"
branch_labels = None
depends_on = None

# Legacy ``ProfileType`` enum value stored for company profiles
# (see app/models/enums.py: ProfileType.company == "Company").
LEGACY_COMPANY_PROFILE_TYPE = "Company"

# Defaults for converted companies.
DEFAULT_MARKET = "mz"
COMPANY_VERIFICATION_STATUS = "unverified"

# RBAC membership for the converting owner (TenantRole.org_owner,
# MembershipStatus.active).
OWNER_ROLE = "org_owner"
OWNER_STATUS = "active"

# Reversibility markers. Created companies are tagged in ``external_refs`` and
# backfilled audit rows are tagged in their ``after`` payload so the downgrade
# can delete exactly the rows produced here.
COMPANY_MARKER_KEY = "migrated_from_profile"
AUDIT_MARKER_KEY = "_migration"
AUDIT_MARKER_VALUE = revision

# Backfilled audit-trail conventions.
AUDIT_ACTION = "job.status_changed"
AUDIT_TARGET_TYPE = "job"

# Lightweight table references for the data migration.
_users = sa.table(
    "users",
    sa.column("id", postgresql.UUID(as_uuid=True)),
)

_profiles = sa.table(
    "profiles",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("user_id", postgresql.UUID(as_uuid=True)),
    sa.column("name", sa.String()),
    sa.column("type", sa.String()),
)

_companies = sa.table(
    "companies",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("name", sa.String()),
    sa.column("slug", sa.String()),
    sa.column("market", sa.String()),
    sa.column("verification_status", sa.String()),
    sa.column("created_by", postgresql.UUID(as_uuid=True)),
    sa.column("external_refs", postgresql.JSONB(astext_type=sa.Text())),
)

_memberships = sa.table(
    "memberships",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("user_id", postgresql.UUID(as_uuid=True)),
    sa.column("company_id", postgresql.UUID(as_uuid=True)),
    sa.column("role", sa.String()),
    sa.column("status", sa.String()),
)

_jobs = sa.table(
    "jobs",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("status_history", postgresql.JSONB(astext_type=sa.Text())),
)

_audit_logs = sa.table(
    "audit_logs",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("actor_id", postgresql.UUID(as_uuid=True)),
    sa.column("actor_label", sa.String()),
    sa.column("action", sa.String()),
    sa.column("target_type", sa.String()),
    sa.column("target_id", postgresql.UUID(as_uuid=True)),
    sa.column("before", postgresql.JSONB(astext_type=sa.Text())),
    sa.column("after", postgresql.JSONB(astext_type=sa.Text())),
    sa.column("created_at", sa.DateTime(timezone=True)),
)


def _slugify(value: str) -> str:
    """Mirror ``Job.slug`` generation: ASCII-fold, lowercase, hyphenate."""
    normalized = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized.lower()).strip("-")
    return slug or "company"


def _unique_slug(base: str, taken: set[str]) -> str:
    """Return ``base`` (or ``base-2``, ``base-3`` …) not already in ``taken``."""
    candidate = base
    suffix = 2
    while candidate in taken:
        candidate = f"{base}-{suffix}"
        suffix += 1
    taken.add(candidate)
    return candidate


def _parse_timestamp(value: Any) -> datetime | None:
    """Parse an ISO-8601 ``status_history`` timestamp, tolerating a ``Z`` suffix."""
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _split_actor(by: Any, known_user_ids: set[UUID]) -> tuple[UUID | None, str | None]:
    """Map a status-history ``by`` value onto (actor_id, actor_label).

    A value that parses to a known user id becomes ``actor_id``; anything else
    (a worker label such as ``worker:expire_old_jobs``, or an unknown id) is kept
    verbatim in ``actor_label`` so attribution is never lost.
    """
    if by is None:
        return None, None
    text = str(by).strip()
    if not text:
        return None, None
    try:
        candidate = UUID(text)
    except (ValueError, AttributeError):
        return None, text
    if candidate in known_user_ids:
        return candidate, None
    return None, text


def upgrade() -> None:
    bind = op.get_bind()

    # --- 1. Convert company profiles into companies + owner memberships -------
    known_user_ids = {row.id for row in bind.execute(sa.select(_users.c.id)).fetchall()}

    # Seed the per-market slug registry with slugs already present so converted
    # companies never collide with existing rows (uq_companies_market_slug).
    taken_slugs: dict[str, set[str]] = {}
    for row in bind.execute(sa.select(_companies.c.market, _companies.c.slug)).fetchall():
        taken_slugs.setdefault(row.market, set()).add(row.slug)

    company_profiles = bind.execute(
        sa.select(_profiles.c.id, _profiles.c.user_id, _profiles.c.name).where(
            _profiles.c.type == LEGACY_COMPANY_PROFILE_TYPE
        )
    ).fetchall()

    for profile in company_profiles:
        market = DEFAULT_MARKET
        market_slugs = taken_slugs.setdefault(market, set())
        slug = _unique_slug(_slugify(profile.name), market_slugs)
        company_id = uuid4()

        bind.execute(
            _companies.insert().values(
                id=company_id,
                name=profile.name,
                slug=slug,
                market=market,
                verification_status=COMPANY_VERIFICATION_STATUS,
                created_by=profile.user_id,
                external_refs={COMPANY_MARKER_KEY: str(profile.id)},
            )
        )
        bind.execute(
            _memberships.insert().values(
                id=uuid4(),
                user_id=profile.user_id,
                company_id=company_id,
                role=OWNER_ROLE,
                status=OWNER_STATUS,
            )
        )

    # --- 2. Anonymous jobs (null company_id) are intentionally left as-is -----
    #         (R23.3); no action required.

    # --- 3. Backfill job status_history into the audit trail, in order --------
    jobs = bind.execute(
        sa.select(_jobs.c.id, _jobs.c.status_history).where(_jobs.c.status_history.isnot(None))
    ).fetchall()

    for job in jobs:
        history = job.status_history or []
        if not isinstance(history, list):
            continue
        for entry in history:
            if not isinstance(entry, dict):
                continue
            actor_id, actor_label = _split_actor(entry.get("by"), known_user_ids)

            before = None
            from_status = entry.get("from")
            if from_status is not None:
                before = {"status": from_status}

            after: dict[str, Any] = {"status": entry.get("to"), AUDIT_MARKER_KEY: AUDIT_MARKER_VALUE}
            reason = entry.get("reason")
            if reason is not None:
                after["reason"] = reason

            values: dict[str, Any] = {
                "id": uuid4(),
                "actor_id": actor_id,
                "actor_label": actor_label,
                "action": AUDIT_ACTION,
                "target_type": AUDIT_TARGET_TYPE,
                "target_id": job.id,
                "before": before,
                "after": after,
            }
            created_at = _parse_timestamp(entry.get("at"))
            if created_at is not None:
                values["created_at"] = created_at

            bind.execute(_audit_logs.insert().values(**values))


def downgrade() -> None:
    bind = op.get_bind()

    # Reverse step 3: delete only the audit rows backfilled by this migration,
    # identified by the marker embedded in their ``after`` payload.
    bind.execute(
        _audit_logs.delete().where(
            sa.text("after ->> :key = :value").bindparams(key=AUDIT_MARKER_KEY, value=AUDIT_MARKER_VALUE)
        )
    )

    # Reverse step 1: find the companies this migration created (tagged in
    # ``external_refs``), drop their owner memberships, then the companies.
    migrated_company_ids = [
        row.id
        for row in bind.execute(
            sa.select(_companies.c.id).where(
                sa.text("external_refs ->> :key IS NOT NULL").bindparams(key=COMPANY_MARKER_KEY)
            )
        ).fetchall()
    ]
    if migrated_company_ids:
        bind.execute(_memberships.delete().where(_memberships.c.company_id.in_(migrated_company_ids)))
        bind.execute(_companies.delete().where(_companies.c.id.in_(migrated_company_ids)))
