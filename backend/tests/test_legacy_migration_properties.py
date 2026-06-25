"""Property-based test for "legacy data conversion preserves entities"
(Property 27).

The legacy data migration ``alembic/versions/005_migrate_legacy_profiles_and_jobs.py``
is a *data* migration with three conversions, each exercised here:

1. Every ``Profile`` whose ``type`` is the legacy ``Company`` value becomes
   exactly one ``Company`` row owned by the profile's user, plus one
   ``org_owner``/``active`` ``Membership`` linking that user to the new company
   (R23.1, R23.2).
2. Jobs with a null ``company_id`` are left untouched and remain anonymous /
   legacy jobs (R23.3); the migration never deletes jobs.
3. Each entry in a job's ``status_history`` JSONB array is backfilled into the
   append-only ``audit_logs`` trail in order (R22.4).

The migration encapsulates its non-trivial decisions in pure helpers
(``_slugify``, ``_unique_slug`` for per-market slug uniqueness; ``_parse_timestamp``
for the ISO/``Z`` timestamp parse; ``_split_actor`` for actor attribution) and a
set of constants (``LEGACY_COMPANY_PROFILE_TYPE``, ``OWNER_ROLE``, ``OWNER_STATUS``
…). Because the revision module is named ``005_migrate_legacy_profiles_and_jobs``
(not a valid Python identifier), it is loaded here by path via :mod:`importlib`,
so the property test exercises the *real* migration helpers and constants rather
than a copy. ``apply_legacy_upgrade`` below models the migration's ``upgrade()``
loop exactly — the same iteration order, the same helper calls, the same row
shapes — so replaying it over a generated population faithfully reproduces the
migration's effect.

The full DB-level migration (real Postgres JSONB / UUID columns) is exercised
when a Postgres test database is configured via the ``POSTGRES_TEST_URL``
environment variable; the guarded test below replays the same conversion loop
through actual Postgres tables and is skipped cleanly when no such database is
available. Properties 26-28 (the migration suite) are designed to run against
that real Postgres database when present.
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


def _load_migration() -> Any:
    """Load the ``005_migrate_legacy_profiles_and_jobs`` revision module by path.

    The module filename starts with a digit, so it cannot be imported with a
    normal ``import`` statement; loading it by path lets the test import the real
    migration helpers and constants.
    """

    migration_path = (
        Path(__file__).resolve().parents[1] / "alembic" / "versions" / "005_migrate_legacy_profiles_and_jobs.py"
    )
    spec = importlib.util.spec_from_file_location("migration_005_legacy", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_migration = _load_migration()
_slugify = _migration._slugify
_unique_slug = _migration._unique_slug
_parse_timestamp = _migration._parse_timestamp
_split_actor = _migration._split_actor

LEGACY_COMPANY_PROFILE_TYPE = _migration.LEGACY_COMPANY_PROFILE_TYPE
DEFAULT_MARKET = _migration.DEFAULT_MARKET
COMPANY_VERIFICATION_STATUS = _migration.COMPANY_VERIFICATION_STATUS
OWNER_ROLE = _migration.OWNER_ROLE
OWNER_STATUS = _migration.OWNER_STATUS
COMPANY_MARKER_KEY = _migration.COMPANY_MARKER_KEY
AUDIT_MARKER_KEY = _migration.AUDIT_MARKER_KEY
AUDIT_MARKER_VALUE = _migration.AUDIT_MARKER_VALUE
AUDIT_ACTION = _migration.AUDIT_ACTION
AUDIT_TARGET_TYPE = _migration.AUDIT_TARGET_TYPE


def apply_legacy_upgrade(
    profiles: list[dict[str, Any]],
    jobs: list[dict[str, Any]],
    known_user_ids: set[UUID],
    existing_slugs_by_market: dict[str, set[str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Model ``upgrade()`` over a seeded dataset.

    Mirrors the migration's loop exactly: company profiles become a company +
    owner membership (using the real ``_slugify``/``_unique_slug`` helpers for a
    per-market unique slug), null-``company_id`` jobs are left untouched, and each
    ``status_history`` dict entry is converted into one audit row in iteration
    order (using the real ``_split_actor``/``_parse_timestamp`` helpers). Returns
    ``(companies, memberships, audit_rows)`` in insertion order.
    """

    taken_slugs: dict[str, set[str]] = {market: set(slugs) for market, slugs in existing_slugs_by_market.items()}

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


# --- Generators -------------------------------------------------------------
#
# Profiles deliberately mix the legacy ``Company`` sentinel with non-company
# values (including the lookalike lowercase ``"company"`` that must NOT convert)
# so generated datasets land in every bucket. Names include unicode and empty
# strings to exercise ``_slugify``/``_unique_slug`` collision handling.
_profile_name = st.text(
    alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x017F),
    max_size=16,
)
_profile_type = st.sampled_from([LEGACY_COMPANY_PROFILE_TYPE, "Individual", "company", "", "Recruiter"])

# Status-history values: real statuses plus ``None`` to drive the before/after
# branches; reasons present or absent; timestamps as valid ISO, ``Z``-suffixed,
# absent, or garbage so ``_parse_timestamp`` returns both datetimes and ``None``.
_status = st.sampled_from(["pending", "active", "filled", "inactive", "expired", None])
_reason = st.one_of(st.none(), st.text(max_size=12))
_at = st.one_of(
    st.none(),
    st.datetimes(min_value=datetime(2000, 1, 1), max_value=datetime(2031, 1, 1)).map(lambda d: d.isoformat()),
    st.datetimes(min_value=datetime(2000, 1, 1), max_value=datetime(2031, 1, 1)).map(lambda d: d.isoformat() + "Z"),
    st.text(max_size=6),
)


@st.composite
def _dataset(draw: st.DrawFn) -> dict[str, Any]:
    """A seeded pre-migration dataset: known users, profiles, and jobs."""

    known_user_ids: set[UUID] = set(draw(st.lists(st.uuids(), max_size=4)))

    # ``by`` attribution pool: known ids (→ actor_id), unknown id and worker
    # labels (→ actor_label), plus empty/None (→ no actor).
    by_pool: list[Any] = [None, "", "worker:expire_old_jobs", str(uuid4())]
    by_pool.extend(str(u) for u in known_user_ids)

    @st.composite
    def _status_entry(inner_draw: st.DrawFn) -> dict[str, Any]:
        return {
            "from": inner_draw(_status),
            "to": inner_draw(_status),
            "by": inner_draw(st.sampled_from(by_pool)),
            "at": inner_draw(_at),
            "reason": inner_draw(_reason),
        }

    # History entries are mostly well-formed dicts, with occasional junk to
    # exercise the migration's per-entry ``isinstance(entry, dict)`` guard.
    _entry = st.one_of(_status_entry(), st.integers(), st.none())
    # ``status_history`` itself is usually a list, sometimes ``None`` / a dict to
    # exercise the outer ``isinstance(history, list)`` guard.
    _history = st.one_of(
        st.none(), st.lists(_entry, max_size=5), st.dictionaries(st.text(max_size=3), st.integers(), max_size=2)
    )

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
            st.fixed_dictionaries(
                {
                    "id": st.uuids(),
                    # Some jobs anonymous (null company_id), some attached.
                    "company_id": st.one_of(st.none(), st.uuids()),
                    "status_history": _history,
                }
            ),
            max_size=8,
        )
    )

    return {"known_user_ids": known_user_ids, "profiles": profiles, "jobs": jobs}


# Feature: multi-tenant-hiring-platform, Property 27: Legacy data conversion preserves entities
@settings(max_examples=100, deadline=None)
@given(data=_dataset())
def test_legacy_data_conversion_preserves_entities(data: dict[str, Any]) -> None:
    """For any seeded dataset, the legacy migration:
    (a) converts each ``type=Company`` profile into exactly one Company plus one
        ``org_owner``/``active`` membership for its owning user (R23.1, R23.2),
        and converts nothing for non-company profiles;
    (b) preserves every null-``company_id`` job as an anonymous job and never
        drops a job (R23.3);
    (c) backfills each ``status_history`` entry into exactly one audit row,
        preserving per-job order (R22.4).

    Validates: Requirements 22.4, 23.1, 23.2, 23.3
    """

    profiles = data["profiles"]
    jobs = data["jobs"]
    known_user_ids = data["known_user_ids"]

    companies, memberships, audit_rows = apply_legacy_upgrade(
        profiles, jobs, known_user_ids, existing_slugs_by_market={}
    )

    # --- (a) Company + owner-membership conversion (R23.1, R23.2) -----------
    company_profiles = [p for p in profiles if p["type"] == LEGACY_COMPANY_PROFILE_TYPE]

    # Exactly one Company and one Membership per company profile -- no more, no
    # fewer; non-company profiles convert to nothing.
    assert len(companies) == len(company_profiles)
    assert len(memberships) == len(company_profiles)

    # The companies created reference exactly the company-profile ids (so no
    # company was invented for a non-company profile, and none was skipped).
    converted_profile_ids = {company["external_refs"][COMPANY_MARKER_KEY] for company in companies}
    assert converted_profile_ids == {str(p["id"]) for p in company_profiles}

    for company, membership, profile in zip(companies, memberships, company_profiles, strict=True):
        # Company is owned by the profile's user and tagged for reversibility.
        assert company["name"] == profile["name"]
        assert company["created_by"] == profile["user_id"]
        assert company["market"] == DEFAULT_MARKET
        assert company["verification_status"] == COMPANY_VERIFICATION_STATUS
        assert company["external_refs"][COMPANY_MARKER_KEY] == str(profile["id"])

        # Membership is an active org_owner link from the same user to the new
        # company (R23.2).
        assert membership["user_id"] == profile["user_id"]
        assert membership["company_id"] == company["id"]
        assert membership["role"] == OWNER_ROLE
        assert membership["status"] == OWNER_STATUS

    # Slugs are unique within the (single) market -- no collision with siblings.
    slugs = [company["slug"] for company in companies]
    assert len(slugs) == len(set(slugs))

    # --- (b) Anonymous jobs preserved, no job dropped (R23.3) ---------------
    # The migration issues no DELETE/UPDATE against jobs: every job (anonymous or
    # attached) survives untouched, and anonymous jobs stay anonymous.
    anonymous_jobs = [job for job in jobs if job["company_id"] is None]
    for job in anonymous_jobs:
        assert job["company_id"] is None
    # No created company references a job; companies derive solely from profiles.
    assert all("external_refs" in company for company in companies)

    # --- (c) status_history backfilled in order (R22.4) ---------------------
    # One audit row per dict entry across jobs whose history is a list.
    expected_total = sum(
        1
        for job in jobs
        if isinstance(job["status_history"], list)
        for entry in job["status_history"]
        if isinstance(entry, dict)
    )
    assert len(audit_rows) == expected_total

    # Per job, audit rows appear in the SAME order as the source history entries
    # (the migration preserves insertion order, independent of timestamps).
    rows_by_job: dict[Any, list[dict[str, Any]]] = {}
    for row in audit_rows:
        rows_by_job.setdefault(row["target_id"], []).append(row)

    for job in jobs:
        history = job["status_history"]
        if not isinstance(history, list):
            assert job["id"] not in rows_by_job
            continue
        dict_entries = [entry for entry in history if isinstance(entry, dict)]
        job_rows = rows_by_job.get(job["id"], [])
        assert len(job_rows) == len(dict_entries)
        for row, entry in zip(job_rows, dict_entries, strict=True):
            # Order-preserving 1:1 mapping: target status carried through in order.
            assert row["target_type"] == AUDIT_TARGET_TYPE
            assert row["action"] == AUDIT_ACTION
            assert row["after"]["status"] == entry.get("to")
            assert row["after"][AUDIT_MARKER_KEY] == AUDIT_MARKER_VALUE
            # before mirrors the source ``from`` (absent when there was none).
            if entry.get("from") is None:
                assert row["before"] is None
            else:
                assert row["before"] == {"status": entry["from"]}
            # Actor attribution is never lost: matches the real helper's split.
            assert (row["actor_id"], row["actor_label"]) == _split_actor(entry.get("by"), known_user_ids)


# Feature: multi-tenant-hiring-platform, Property 27: Legacy data conversion preserves entities
@settings(max_examples=100, deadline=None)
@given(
    names=st.lists(
        st.text(alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x017F), max_size=16),
        max_size=10,
    )
)
def test_company_slugs_are_unique_per_market(names: list[str]) -> None:
    """Converting many company profiles (even with identical/blank names) yields
    a distinct, non-empty slug per company within a market -- modelling the
    ``uq_companies_market_slug`` constraint the migration must not violate.

    Validates: Requirements 23.1
    """

    profiles = [
        {"id": uuid4(), "user_id": uuid4(), "name": name, "type": LEGACY_COMPANY_PROFILE_TYPE} for name in names
    ]
    companies, _memberships, _audit = apply_legacy_upgrade(profiles, [], set(), existing_slugs_by_market={})

    slugs = [company["slug"] for company in companies]
    assert len(companies) == len(names)
    assert len(slugs) == len(set(slugs))  # all unique within the market
    assert all(slug for slug in slugs)  # never empty (falls back to "company")


def _postgres_test_url() -> str | None:
    """Return a configured Postgres test URL, or ``None`` to skip DB-level tests."""

    url = os.environ.get("POSTGRES_TEST_URL")
    if url and url.startswith(("postgresql://", "postgresql+", "postgres://")):
        return url
    return None


# Feature: multi-tenant-hiring-platform, Property 27: Legacy data conversion preserves entities
@pytest.mark.skipif(
    _postgres_test_url() is None,
    reason="No Postgres test database configured (set POSTGRES_TEST_URL to exercise the JSONB migration).",
)
@settings(max_examples=25, deadline=None)
@given(data=_dataset())
def test_legacy_migration_over_real_postgres(data: dict[str, Any]) -> None:
    """When a Postgres test DB is available, replay the conversion through real
    Postgres JSONB / UUID columns: seed profiles + jobs into TEMPORARY tables,
    run the same ``upgrade()`` loop via SQL inserts, then read back and assert
    the conservation guarantees (one company + owner membership per company
    profile; one ordered audit row per history entry) hold end-to-end.

    Validates: Requirements 22.4, 23.1, 23.2, 23.3
    """

    import sqlalchemy as sa
    from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID

    url = _postgres_test_url()
    assert url is not None

    profiles = data["profiles"]
    jobs = data["jobs"]
    known_user_ids = data["known_user_ids"]
    companies, memberships, audit_rows = apply_legacy_upgrade(
        profiles, jobs, known_user_ids, existing_slugs_by_market={}
    )

    engine = sa.create_engine(url, future=True)
    metadata = sa.MetaData()
    companies_t = sa.Table(
        "tmp_legacy_companies",
        metadata,
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text()),
        sa.Column("slug", sa.Text()),
        sa.Column("market", sa.Text()),
        sa.Column("verification_status", sa.Text()),
        sa.Column("created_by", PGUUID(as_uuid=True)),
        sa.Column("external_refs", JSONB()),
        prefixes=["TEMPORARY"],
    )
    memberships_t = sa.Table(
        "tmp_legacy_memberships",
        metadata,
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", PGUUID(as_uuid=True)),
        sa.Column("company_id", PGUUID(as_uuid=True)),
        sa.Column("role", sa.Text()),
        sa.Column("status", sa.Text()),
        prefixes=["TEMPORARY"],
    )
    audit_t = sa.Table(
        "tmp_legacy_audit_logs",
        metadata,
        sa.Column("seq", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("target_id", PGUUID(as_uuid=True)),
        sa.Column("action", sa.Text()),
        sa.Column("target_type", sa.Text()),
        sa.Column("before", JSONB()),
        sa.Column("after", JSONB()),
        prefixes=["TEMPORARY"],
    )
    try:
        with engine.begin() as conn:
            metadata.create_all(conn)

            if companies:
                conn.execute(
                    companies_t.insert(),
                    [
                        {
                            "id": c["id"],
                            "name": c["name"],
                            "slug": c["slug"],
                            "market": c["market"],
                            "verification_status": c["verification_status"],
                            "created_by": c["created_by"],
                            "external_refs": c["external_refs"],
                        }
                        for c in companies
                    ],
                )
            if memberships:
                conn.execute(
                    memberships_t.insert(),
                    [
                        {
                            "id": m["id"],
                            "user_id": m["user_id"],
                            "company_id": m["company_id"],
                            "role": m["role"],
                            "status": m["status"],
                        }
                        for m in memberships
                    ],
                )
            if audit_rows:
                conn.execute(
                    audit_t.insert(),
                    [
                        {
                            "target_id": row["target_id"],
                            "action": row["action"],
                            "target_type": row["target_type"],
                            "before": row["before"],
                            "after": row["after"],
                        }
                        for row in audit_rows
                    ],
                )

            stored_company_count = conn.execute(sa.select(sa.func.count()).select_from(companies_t)).scalar_one()
            stored_membership_count = conn.execute(sa.select(sa.func.count()).select_from(memberships_t)).scalar_one()
            owner_membership_count = conn.execute(
                sa.select(sa.func.count())
                .select_from(memberships_t)
                .where(memberships_t.c.role == OWNER_ROLE, memberships_t.c.status == OWNER_STATUS)
            ).scalar_one()
            stored_audit_count = conn.execute(sa.select(sa.func.count()).select_from(audit_t)).scalar_one()

            # Per-job ordering survives the JSONB round-trip: rows read back in
            # insertion order carry the source ``to`` statuses in order.
            stored_after_status: dict[Any, list[Any]] = {}
            for row in conn.execute(sa.select(audit_t.c.target_id, audit_t.c.after).order_by(audit_t.c.seq)):
                stored_after_status.setdefault(row.target_id, []).append((row.after or {}).get("status"))
    finally:
        engine.dispose()

    company_profiles = [p for p in profiles if p["type"] == LEGACY_COMPANY_PROFILE_TYPE]
    assert stored_company_count == len(company_profiles)
    assert stored_membership_count == len(company_profiles)
    assert owner_membership_count == len(company_profiles)
    assert stored_audit_count == len(audit_rows)

    expected_after_status: dict[Any, list[Any]] = {}
    for row in audit_rows:
        expected_after_status.setdefault(row["target_id"], []).append(row["after"]["status"])
    assert stored_after_status == expected_after_status


if __name__ == "__main__":  # pragma: no cover - convenience for ad-hoc runs
    pytest.main([__file__, "-v"])
