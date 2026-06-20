"""Property-based test for "admin migration maps legacy admins and loses no
accounts" (Property 26).

The RBAC migration ``alembic/versions/004_migrate_admins.py`` is a *data*
migration: it walks every ``users`` row and rewrites the free-form ``roles``
``text[]`` column, replacing the legacy value ``"admin"`` with the RBAC
``platform_super_admin`` Platform_Role (R6.1), while never deleting an account
(R6.3) and preserving every other role (de-duplicated, order-stable).

The migration's mapping is exposed as a pure helper, ``_remap_roles``, together
with the ``LEGACY_ADMIN`` / ``PLATFORM_SUPER_ADMIN`` constants. Because the
revision module is named ``004_migrate_admins`` (not a valid Python identifier),
it is loaded here by path via :mod:`importlib`, so the property test exercises
the *real* migration mapping rather than a copy. ``upgrade()`` applies exactly
``_remap_roles(roles, LEGACY_ADMIN, PLATFORM_SUPER_ADMIN)`` to each row, so
replaying that helper over a generated population of users faithfully models the
migration's effect on account roles.

The full DB-level migration (running ``alembic upgrade``/``downgrade`` against a
real ``text[]`` column) is exercised when a Postgres test database is configured
via the ``POSTGRES_TEST_URL`` environment variable; the guarded test below runs
the same mapping through an actual Postgres array column and is skipped cleanly
when no such database is available. Properties 26-28 (the migration suite) are
designed to run against that real Postgres database when present.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


def _load_migration() -> Any:
    """Load the ``004_migrate_admins`` revision module by path.

    The module filename starts with a digit, so it cannot be imported with a
    normal ``import`` statement; loading it by path lets the test import the
    real migration mapping helper and constants.
    """

    migration_path = (
        Path(__file__).resolve().parents[1] / "alembic" / "versions" / "004_migrate_admins.py"
    )
    spec = importlib.util.spec_from_file_location("migration_004_migrate_admins", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_migration = _load_migration()
_remap_roles = _migration._remap_roles
LEGACY_ADMIN = _migration.LEGACY_ADMIN
PLATFORM_SUPER_ADMIN = _migration.PLATFORM_SUPER_ADMIN


def apply_admin_upgrade(users: dict[UUID, list[str]]) -> dict[UUID, list[str]]:
    """Model ``upgrade()`` over a population of users.

    Mirrors the migration loop exactly: for each user, apply the real
    ``_remap_roles`` helper; rows it leaves unchanged (returns ``None``) keep
    their original roles. The account set is preserved key-for-key -- the
    migration only ever issues UPDATEs, never DELETEs.
    """

    result: dict[UUID, list[str]] = {}
    for user_id, roles in users.items():
        remapped = _remap_roles(roles, LEGACY_ADMIN, PLATFORM_SUPER_ADMIN)
        result[user_id] = remapped if remapped is not None else list(roles)
    return result


# Roles are free-form legacy strings. The pool deliberately mixes the legacy
# "admin" sentinel, the target RBAC role, and unrelated values so generated
# users land in every meaningful bucket: pure admins, admins with extra roles,
# users that already carry the target role, and non-admins.
_role = st.sampled_from(
    [LEGACY_ADMIN, PLATFORM_SUPER_ADMIN, "moderator", "support", "employer", "candidate", "user"]
)
_role_list = st.lists(_role, max_size=6)


@st.composite
def _user_population(draw: st.DrawFn) -> dict[UUID, list[str]]:
    """A set of users keyed by unique identity, each with an arbitrary role list."""

    role_lists = draw(st.lists(_role_list, max_size=12))
    return {uuid4(): roles for roles in role_lists}


# Feature: multi-tenant-hiring-platform, Property 26: Admin migration maps legacy admins and loses no accounts
@settings(max_examples=100, deadline=None)
@given(users=_user_population())
def test_admin_migration_maps_legacy_admins_and_loses_no_accounts(
    users: dict[UUID, list[str]],
) -> None:
    """For any set of existing users, after the RBAC admin migration:
    (a) every user whose legacy roles contained ``"admin"`` holds
        ``platform_super_admin``;
    (b) no other user gains ``platform_super_admin``; and
    (c) the set of user accounts (by identity) is preserved with no loss.

    Validates: Requirements 6.1, 6.3, 23.4
    """

    migrated = apply_admin_upgrade(users)

    # (c) Conservation (R23.4): exactly the same account identities survive --
    # none dropped, none invented.
    assert set(migrated.keys()) == set(users.keys())
    assert len(migrated) == len(users)

    for user_id, original_roles in users.items():
        was_legacy_admin = LEGACY_ADMIN in original_roles
        new_roles = migrated[user_id]
        had_target = PLATFORM_SUPER_ADMIN in original_roles
        has_target = PLATFORM_SUPER_ADMIN in new_roles

        # Every non-"admin" role the account held is preserved (no collateral
        # loss of access).
        preserved = {r for r in original_roles if r != LEGACY_ADMIN}
        assert preserved <= set(new_roles)

        if was_legacy_admin:
            # (a) Legacy admins are promoted to the RBAC super-admin role (R6.1).
            assert has_target
            # The legacy sentinel itself is fully replaced, never left behind,
            # and the remapped row is de-duplicated.
            assert LEGACY_ADMIN not in new_roles
            assert len(new_roles) == len(set(new_roles))
        else:
            # (b) A non-admin never *gains* the target role: rows without the
            # legacy sentinel are left untouched -- byte-for-byte identical to
            # the original, so they cannot acquire ``platform_super_admin``.
            assert new_roles == list(original_roles)
            assert has_target == had_target


# Feature: multi-tenant-hiring-platform, Property 26: Admin migration maps legacy admins and loses no accounts
@settings(max_examples=100, deadline=None)
@given(roles=_role_list)
def test_remap_roles_is_idempotent_and_order_stable(roles: list[str]) -> None:
    """Re-applying the mapping after migration is a no-op: once ``"admin"`` is
    gone there is nothing left to remap, so the migrated roles are stable. The
    first remap also preserves the relative order of surviving roles.

    Validates: Requirements 6.1, 6.3
    """

    first = _remap_roles(roles, LEGACY_ADMIN, PLATFORM_SUPER_ADMIN)
    effective = first if first is not None else list(roles)

    # Idempotence: a second upgrade finds no legacy admin to remap.
    second = _remap_roles(effective, LEGACY_ADMIN, PLATFORM_SUPER_ADMIN)
    assert second is None

    if first is not None:
        # Order stability: surviving roles keep their first-seen order, with the
        # legacy sentinel mapped to the target in place.
        expected: list[str] = []
        seen: set[str] = set()
        for role in roles:
            mapped = PLATFORM_SUPER_ADMIN if role == LEGACY_ADMIN else role
            if mapped not in seen:
                seen.add(mapped)
                expected.append(mapped)
        assert first == expected


def _postgres_test_url() -> str | None:
    """Return a configured Postgres test URL, or ``None`` to skip DB-level tests."""

    url = os.environ.get("POSTGRES_TEST_URL")
    if url and url.startswith(("postgresql://", "postgresql+", "postgres://")):
        return url
    return None


# Feature: multi-tenant-hiring-platform, Property 26: Admin migration maps legacy admins and loses no accounts
@pytest.mark.skipif(
    _postgres_test_url() is None,
    reason="No Postgres test database configured (set POSTGRES_TEST_URL to exercise the text[] migration).",
)
@settings(max_examples=25, deadline=None)
@given(users=_user_population())
def test_admin_migration_over_real_postgres_array(users: dict[UUID, list[str]]) -> None:
    """When a Postgres test DB is available, exercise the migration mapping
    through a real ``text[]`` column: seed users, apply the migration helper via
    SQL UPDATEs exactly as ``upgrade()`` does, and assert the same mapping and
    conservation guarantees hold end-to-end.

    Validates: Requirements 6.1, 6.3, 23.4
    """

    import sqlalchemy as sa
    from sqlalchemy.dialects.postgresql import ARRAY, UUID as PGUUID

    url = _postgres_test_url()
    assert url is not None
    engine = sa.create_engine(url, future=True)
    metadata = sa.MetaData()
    table = sa.Table(
        "tmp_admin_migration_users",
        metadata,
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("roles", ARRAY(sa.Text()), nullable=False),
        prefixes=["TEMPORARY"],
    )
    try:
        with engine.begin() as conn:
            metadata.create_all(conn)
            if users:
                conn.execute(
                    table.insert(),
                    [{"id": uid, "roles": roles} for uid, roles in users.items()],
                )

            # Replay upgrade(): read each row and UPDATE remapped roles in place.
            rows = conn.execute(sa.select(table.c.id, table.c.roles)).fetchall()
            for row in rows:
                new_roles = _remap_roles(row.roles, LEGACY_ADMIN, PLATFORM_SUPER_ADMIN)
                if new_roles is not None:
                    conn.execute(table.update().where(table.c.id == row.id).values(roles=new_roles))

            stored = {row.id: list(row.roles) for row in conn.execute(sa.select(table.c.id, table.c.roles))}
    finally:
        engine.dispose()

    expected = apply_admin_upgrade(users)
    assert set(stored.keys()) == set(users.keys())
    assert stored == expected


if __name__ == "__main__":  # pragma: no cover - convenience for ad-hoc runs
    pytest.main([__file__, "-v"])
