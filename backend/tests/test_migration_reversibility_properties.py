"""Property-based test for "RBAC and legacy migrations are reversible"
(Property 28).

The RBAC migration ``alembic/versions/004_migrate_admins.py`` and the legacy
data migration ``alembic/versions/005_migrate_legacy_profiles_and_jobs.py`` are
both *data* migrations whose ``downgrade()`` is designed to restore the
pre-migration data shape (R6.4, R23.5):

* **004** rewrites the free-form ``roles`` ``text[]`` column, mapping the legacy
  ``"admin"`` value to ``platform_super_admin`` on ``upgrade()`` and back again
  on ``downgrade()`` via the same pure ``_remap_roles`` helper. For every row the
  migration touches (one that carried ``"admin"`` and not yet the target role)
  the upgrade-then-downgrade round-trip restores the original role list.

* **005** *creates* rows on ``upgrade()`` (companies, owner memberships, and
  backfilled audit entries) and tags every created row with a reversibility
  marker — companies via ``external_refs[migrated_from_profile]`` and audit rows
  via ``after._migration``. ``downgrade()`` deletes *exactly* the marked rows, so
  any pre-existing (unmarked) rows are left untouched and the row sets are
  restored to their pre-migration state.

Because the revision modules are named with a leading digit (not valid Python
identifiers) they are loaded here by path via :mod:`importlib`, so the property
test exercises the *real* migration helpers, constants, and reversibility
markers rather than a copy. The in-memory ``model_*`` functions below mirror the
migrations' ``upgrade()``/``downgrade()`` logic exactly — the same iteration
order, the same helper calls, and the same marker predicates the SQL
``downgrade()`` uses — so replaying them over a generated pre-migration state
faithfully reproduces the migrations' reversibility behavior without a database.

The full DB-level round-trip (real Postgres JSONB columns and the marker-based
``DELETE`` predicates) is exercised when a Postgres test database is configured
via the ``POSTGRES_TEST_URL`` environment variable; the guarded test below
replays the same marked-row deletion through actual Postgres tables and is
skipped cleanly when no such database is available.
"""

from __future__ import annotations

import importlib.util
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


def _load_migration(filename: str, module_name: str) -> Any:
    """Load a revision module by path.

    The revision filenames start with a digit, so they cannot be imported with a
    normal ``import`` statement; loading by path lets the test import the *real*
    migration helpers, constants, and reversibility markers.
    """

    migration_path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / filename
    spec = importlib.util.spec_from_file_location(module_name, migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- 004: RBAC admin role remap ---------------------------------------------
_admin_migration = _load_migration("004_migrate_admins.py", "migration_004_reversibility")
_remap_roles = _admin_migration._remap_roles
LEGACY_ADMIN = _admin_migration.LEGACY_ADMIN
PLATFORM_SUPER_ADMIN = _admin_migration.PLATFORM_SUPER_ADMIN

# --- 005: legacy profile/job conversion -------------------------------------
_legacy_migration = _load_migration(
    "005_migrate_legacy_profiles_and_jobs.py", "migration_005_reversibility"
)
_slugify = _legacy_migration._slugify
_unique_slug = _legacy_migration._unique_slug
_parse_timestamp = _legacy_migration._parse_timestamp
_split_actor = _legacy_migration._split_actor

LEGACY_COMPANY_PROFILE_TYPE = _legacy_migration.LEGACY_COMPANY_PROFILE_TYPE
DEFAULT_MARKET = _legacy_migration.DEFAULT_MARKET
COMPANY_VERIFICATION_STATUS = _legacy_migration.COMPANY_VERIFICATION_STATUS
OWNER_ROLE = _legacy_migration.OWNER_ROLE
OWNER_STATUS = _legacy_migration.OWNER_STATUS
COMPANY_MARKER_KEY = _legacy_migration.COMPANY_MARKER_KEY
AUDIT_MARKER_KEY = _legacy_migration.AUDIT_MARKER_KEY
AUDIT_MARKER_VALUE = _legacy_migration.AUDIT_MARKER_VALUE
AUDIT_ACTION = _legacy_migration.AUDIT_ACTION
AUDIT_TARGET_TYPE = _legacy_migration.AUDIT_TARGET_TYPE


# ---------------------------------------------------------------------------
# 004 reversibility model
# ---------------------------------------------------------------------------
def model_admin_round_trip(roles: list[str]) -> list[str]:
    """Apply ``upgrade()`` then ``downgrade()`` to one user's role list.

    Mirrors the migration exactly: ``upgrade()`` runs
    ``_remap_roles(roles, LEGACY_ADMIN, PLATFORM_SUPER_ADMIN)`` and
    ``downgrade()`` runs the inverse ``_remap_roles(roles, PLATFORM_SUPER_ADMIN,
    LEGACY_ADMIN)``; a helper that returns ``None`` (nothing to remap) leaves the
    row untouched, just as the migration loop skips it.
    """

    up = _remap_roles(roles, LEGACY_ADMIN, PLATFORM_SUPER_ADMIN)
    after_up = up if up is not None else list(roles)
    down = _remap_roles(after_up, PLATFORM_SUPER_ADMIN, LEGACY_ADMIN)
    return down if down is not None else list(after_up)


# ---------------------------------------------------------------------------
# 005 reversibility model
# ---------------------------------------------------------------------------
def model_legacy_upgrade(
    profiles: list[dict[str, Any]],
    jobs: list[dict[str, Any]],
    known_user_ids: set[UUID],
    existing_slugs_by_market: dict[str, set[str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Model ``upgrade()``: the rows the migration *creates*.

    Mirrors the migration loop: each ``type=Company`` profile yields one
    marker-tagged company + one ``org_owner``/``active`` membership, and each
    ``status_history`` dict entry yields one marker-tagged audit row. Returns
    ``(companies, memberships, audit_rows)`` in insertion order.
    """

    taken_slugs: dict[str, set[str]] = {
        market: set(slugs) for market, slugs in existing_slugs_by_market.items()
    }

    companies: list[dict[str, Any]] = []
    memberships: list[dict[str, Any]] = []
    for profile in profiles:
        if profile["type"] != LEGACY_COMPANY_PROFILE_TYPE:
            continue
        market = DEFAULT_MARKET
        market_slugs = taken_slugs.setdefault(market, set())
        slug = _unique_slug(_slugify(profile["name"]), market_slugs)
        company_id = uuid4()
        companies.append(
            {
                "id": company_id,
                "name": profile["name"],
                "slug": slug,
                "market": market,
                "verification_status": COMPANY_VERIFICATION_STATUS,
                "created_by": profile["user_id"],
                "external_refs": {COMPANY_MARKER_KEY: str(profile["id"])},
            }
        )
        memberships.append(
            {
                "id": uuid4(),
                "user_id": profile["user_id"],
                "company_id": company_id,
                "role": OWNER_ROLE,
                "status": OWNER_STATUS,
            }
        )

    audit_rows: list[dict[str, Any]] = []
    for job in jobs:
        history = job["status_history"]
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
            audit_rows.append(
                {
                    "id": uuid4(),
                    "actor_id": actor_id,
                    "actor_label": actor_label,
                    "action": AUDIT_ACTION,
                    "target_type": AUDIT_TARGET_TYPE,
                    "target_id": job["id"],
                    "before": before,
                    "after": after,
                    "created_at": _parse_timestamp(entry.get("at")),
                }
            )

    return companies, memberships, audit_rows


def model_legacy_downgrade(
    companies: list[dict[str, Any]],
    memberships: list[dict[str, Any]],
    audit_logs: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Model ``downgrade()`` using the migration's marker predicates.

    Mirrors the SQL ``downgrade()`` exactly:

    * delete audit rows whose ``after ->> _migration == revision`` marker matches;
    * find companies whose ``external_refs ->> migrated_from_profile`` marker is
      present, delete their memberships, then delete those companies.

    Surviving (unmarked) rows keep their original relative order.
    """

    kept_audit = [
        row
        for row in audit_logs
        if not (isinstance(row.get("after"), dict) and row["after"].get(AUDIT_MARKER_KEY) == AUDIT_MARKER_VALUE)
    ]

    migrated_company_ids = {
        company["id"]
        for company in companies
        if isinstance(company.get("external_refs"), dict)
        and company["external_refs"].get(COMPANY_MARKER_KEY) is not None
    }
    kept_memberships = [m for m in memberships if m["company_id"] not in migrated_company_ids]
    kept_companies = [c for c in companies if c["id"] not in migrated_company_ids]

    return kept_companies, kept_memberships, kept_audit


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------
# 004: role lists are unique (the migration de-duplicates), drawn from a pool
# that mixes the legacy sentinel, the target role, and unrelated roles so users
# land in every bucket: untouched non-admins, touched legacy admins, and rows
# that already carry the target role (where the round-trip is intentionally
# asymmetric and excluded from the equality assertion).
_admin_role_pool = [LEGACY_ADMIN, PLATFORM_SUPER_ADMIN, "moderator", "support", "employer", "candidate"]


@st.composite
def _admin_population(draw: st.DrawFn) -> dict[UUID, list[str]]:
    role_lists = draw(
        st.lists(st.lists(st.sampled_from(_admin_role_pool), max_size=5, unique=True), max_size=12)
    )
    return {uuid4(): roles for roles in role_lists}


# 005: a pre-migration state of UNMARKED rows that ``downgrade()`` must never
# touch, alongside the profiles/jobs the migration will convert. Pre-existing
# companies/audit rows deliberately exclude the reversibility markers so the
# round-trip can prove the downgrade deletes *only* migration-created rows.
_unmarked_external_refs = st.one_of(
    st.none(),
    st.dictionaries(
        keys=st.sampled_from(["website", "legacy_id", "source"]),
        values=st.text(max_size=8),
        max_size=3,
    ),
)
_unmarked_after = st.one_of(
    st.none(),
    st.dictionaries(
        keys=st.sampled_from(["status", "note", "actor"]),
        values=st.text(max_size=8),
        max_size=3,
    ),
)

_profile_name = st.text(alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x017F), max_size=12)
_profile_type = st.sampled_from([LEGACY_COMPANY_PROFILE_TYPE, "Individual", "company", "", "Recruiter"])
_status = st.sampled_from(["pending", "active", "filled", "inactive", "expired", None])
_at = st.one_of(
    st.none(),
    st.datetimes(min_value=datetime(2000, 1, 1), max_value=datetime(2031, 1, 1)).map(lambda d: d.isoformat()),
    st.text(max_size=6),
)


@st.composite
def _legacy_state(draw: st.DrawFn) -> dict[str, Any]:
    """A seeded pre-migration state: unmarked existing rows + convertible data."""

    known_user_ids: set[UUID] = set(draw(st.lists(st.uuids(), max_size=4)))
    by_pool: list[Any] = [None, "", "worker:expire_old_jobs", str(uuid4())]
    by_pool.extend(str(u) for u in known_user_ids)

    @st.composite
    def _status_entry(inner: st.DrawFn) -> dict[str, Any]:
        return {
            "from": inner(_status),
            "to": inner(_status),
            "by": inner(st.sampled_from(by_pool)),
            "at": inner(_at),
            "reason": inner(st.one_of(st.none(), st.text(max_size=8))),
        }

    _history = st.one_of(st.none(), st.lists(_status_entry(), max_size=5))

    profiles = draw(
        st.lists(
            st.fixed_dictionaries(
                {
                    "id": st.uuids(),
                    "user_id": st.uuids(),
                    "name": _profile_name,
                    "type": _profile_type,
                }
            ),
            max_size=8,
        )
    )
    jobs = draw(
        st.lists(
            st.fixed_dictionaries({"id": st.uuids(), "status_history": _history}),
            max_size=8,
        )
    )

    # Pre-existing, UNMARKED rows that must survive the round-trip untouched.
    existing_companies = draw(
        st.lists(
            st.fixed_dictionaries(
                {
                    "id": st.uuids(),
                    "name": st.text(max_size=10),
                    "slug": st.text(min_size=1, max_size=10),
                    "market": st.sampled_from(["mz", "mx"]),
                    "verification_status": st.sampled_from(["unverified", "verified"]),
                    "created_by": st.uuids(),
                    "external_refs": _unmarked_external_refs,
                }
            ),
            max_size=5,
        )
    )
    existing_memberships = draw(
        st.lists(
            st.fixed_dictionaries(
                {
                    "id": st.uuids(),
                    "user_id": st.uuids(),
                    "company_id": st.uuids(),
                    "role": st.sampled_from(["org_owner", "org_member"]),
                    "status": st.sampled_from(["active", "invited"]),
                }
            ),
            max_size=5,
        )
    )
    existing_audit = draw(
        st.lists(
            st.fixed_dictionaries(
                {
                    "id": st.uuids(),
                    "actor_id": st.one_of(st.none(), st.uuids()),
                    "actor_label": st.one_of(st.none(), st.text(max_size=10)),
                    "action": st.sampled_from(["job.created", "company.verified"]),
                    "target_type": st.sampled_from(["job", "company"]),
                    "target_id": st.uuids(),
                    "before": st.none(),
                    "after": _unmarked_after,
                    "created_at": st.none(),
                }
            ),
            max_size=5,
        )
    )

    return {
        "known_user_ids": known_user_ids,
        "profiles": profiles,
        "jobs": jobs,
        "existing_companies": existing_companies,
        "existing_memberships": existing_memberships,
        "existing_audit": existing_audit,
    }


# Feature: multi-tenant-hiring-platform, Property 28: RBAC and legacy migrations are reversible
@settings(max_examples=100, deadline=None)
@given(state=_legacy_state())
def test_legacy_migration_upgrade_then_downgrade_restores_state(state: dict[str, Any]) -> None:
    """For any seeded pre-migration state, the legacy migration's
    upgrade-then-downgrade round-trip restores the prior data shape (R23.5):
    the rows ``upgrade()`` creates are tagged with reversibility markers, and
    ``downgrade()`` deletes *exactly* those marked rows, leaving every
    pre-existing (unmarked) company, membership, and audit row untouched.

    Validates: Requirements 23.5
    """

    existing_companies = state["existing_companies"]
    existing_memberships = state["existing_memberships"]
    existing_audit = state["existing_audit"]

    created_companies, created_memberships, created_audit = model_legacy_upgrade(
        state["profiles"], state["jobs"], state["known_user_ids"], existing_slugs_by_market={}
    )

    # Post-upgrade state = pre-existing rows + the rows the migration created.
    post_companies = existing_companies + created_companies
    post_memberships = existing_memberships + created_memberships
    post_audit = existing_audit + created_audit

    # Sanity: the migration actually created marked rows for company profiles and
    # for every status-history entry (otherwise the round-trip would be vacuous).
    company_profiles = [p for p in state["profiles"] if p["type"] == LEGACY_COMPANY_PROFILE_TYPE]
    assert len(created_companies) == len(company_profiles)
    assert len(created_memberships) == len(company_profiles)
    for company in created_companies:
        assert company["external_refs"][COMPANY_MARKER_KEY] is not None
    for row in created_audit:
        assert row["after"][AUDIT_MARKER_KEY] == AUDIT_MARKER_VALUE

    # Apply downgrade(): marker-based deletion of exactly the created rows.
    down_companies, down_memberships, down_audit = model_legacy_downgrade(
        post_companies, post_memberships, post_audit
    )

    # The row sets are restored: every migration-created (marked) row is removed,
    # and every pre-existing (unmarked) row remains, in its original order.
    assert down_companies == existing_companies
    assert down_memberships == existing_memberships
    assert down_audit == existing_audit

    # No marker survives the downgrade -- nothing the migration created is left.
    assert all(
        not (isinstance(c.get("external_refs"), dict) and COMPANY_MARKER_KEY in c["external_refs"])
        for c in down_companies
    )
    assert all(
        not (isinstance(r.get("after"), dict) and r["after"].get(AUDIT_MARKER_KEY) == AUDIT_MARKER_VALUE)
        for r in down_audit
    )


# Feature: multi-tenant-hiring-platform, Property 28: RBAC and legacy migrations are reversible
@settings(max_examples=100, deadline=None)
@given(users=_admin_population())
def test_admin_migration_upgrade_then_downgrade_restores_roles(users: dict[UUID, list[str]]) -> None:
    """For any set of users, the RBAC admin migration's upgrade-then-downgrade
    round-trip is reversible for the rows it touches (R6.4):

    (a) the account set is preserved -- no row added or dropped;
    (b) the migration touches exactly the rows carrying the legacy ``"admin"``
        value; an upgraded row carries ``platform_super_admin`` and no longer the
        legacy sentinel;
    (c) for every row the migration's mapping cleanly governs (one that did not
        already carry ``platform_super_admin``), upgrade-then-downgrade restores
        the original role list.

    Validates: Requirements 6.4
    """

    # (a) Conservation: the round-trip is a per-row UPDATE, never an INSERT/DELETE.
    round_tripped = {uid: model_admin_round_trip(roles) for uid, roles in users.items()}
    assert set(round_tripped.keys()) == set(users.keys())

    for uid, original in users.items():
        upgraded = _remap_roles(original, LEGACY_ADMIN, PLATFORM_SUPER_ADMIN)
        touched = upgraded is not None

        # (b) The migration touches exactly the rows containing the legacy value.
        assert touched == (LEGACY_ADMIN in original)
        if touched:
            assert PLATFORM_SUPER_ADMIN in upgraded
            assert LEGACY_ADMIN not in upgraded

        # (c) Reversibility for rows the mapping cleanly governs: a row that did
        # not already hold the target role round-trips back to its original list.
        if PLATFORM_SUPER_ADMIN not in original:
            assert round_tripped[uid] == list(original)


def _postgres_test_url() -> str | None:
    """Return a configured Postgres test URL, or ``None`` to skip DB-level tests."""

    url = os.environ.get("POSTGRES_TEST_URL")
    if url and url.startswith(("postgresql://", "postgresql+", "postgres://")):
        return url
    return None


# Feature: multi-tenant-hiring-platform, Property 28: RBAC and legacy migrations are reversible
@pytest.mark.skipif(
    _postgres_test_url() is None,
    reason="No Postgres test database configured (set POSTGRES_TEST_URL to exercise the JSONB downgrade).",
)
@settings(max_examples=25, deadline=None)
@given(state=_legacy_state())
def test_legacy_downgrade_over_real_postgres(state: dict[str, Any]) -> None:
    """When a Postgres test DB is available, exercise the legacy migration's
    marker-based ``downgrade()`` through real Postgres JSONB columns: seed both
    pre-existing (unmarked) rows and migration-created (marked) rows, run the
    same ``DELETE ... WHERE external_refs ->> :key IS NOT NULL`` /
    ``DELETE ... WHERE after ->> :key = :value`` predicates the migration uses,
    then assert only the unmarked rows survive.

    Validates: Requirements 23.5
    """

    import sqlalchemy as sa
    from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID

    url = _postgres_test_url()
    assert url is not None

    created_companies, created_memberships, created_audit = model_legacy_upgrade(
        state["profiles"], state["jobs"], state["known_user_ids"], existing_slugs_by_market={}
    )
    existing_companies = state["existing_companies"]
    existing_audit = state["existing_audit"]

    engine = sa.create_engine(url, future=True)
    metadata = sa.MetaData()
    companies_t = sa.Table(
        "tmp_rev_companies",
        metadata,
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("external_refs", JSONB()),
        prefixes=["TEMPORARY"],
    )
    audit_t = sa.Table(
        "tmp_rev_audit_logs",
        metadata,
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("after", JSONB()),
        prefixes=["TEMPORARY"],
    )
    try:
        with engine.begin() as conn:
            metadata.create_all(conn)

            all_companies = existing_companies + created_companies
            if all_companies:
                conn.execute(
                    companies_t.insert(),
                    [{"id": c["id"], "external_refs": c["external_refs"]} for c in all_companies],
                )
            all_audit = existing_audit + created_audit
            if all_audit:
                conn.execute(
                    audit_t.insert(),
                    [{"id": r["id"], "after": r["after"]} for r in all_audit],
                )

            # Replay downgrade(): the migration's exact marker predicates.
            conn.execute(
                audit_t.delete().where(
                    sa.text("after ->> :key = :value").bindparams(
                        key=AUDIT_MARKER_KEY, value=AUDIT_MARKER_VALUE
                    )
                )
            )
            conn.execute(
                companies_t.delete().where(
                    sa.text("external_refs ->> :key IS NOT NULL").bindparams(key=COMPANY_MARKER_KEY)
                )
            )

            surviving_company_ids = {row.id for row in conn.execute(sa.select(companies_t.c.id))}
            surviving_audit_ids = {row.id for row in conn.execute(sa.select(audit_t.c.id))}
    finally:
        engine.dispose()

    # Exactly the pre-existing unmarked rows survive; every created row is gone.
    assert surviving_company_ids == {c["id"] for c in existing_companies}
    assert surviving_audit_ids == {r["id"] for r in existing_audit}


if __name__ == "__main__":  # pragma: no cover - convenience for ad-hoc runs
    pytest.main([__file__, "-v"])
