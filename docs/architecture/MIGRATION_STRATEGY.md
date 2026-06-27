---
last_verified: 2026-06-27T00:00:00Z
git_ref: master
verified_by: multi-tenant-hiring-platform spec — task 19.1 documentation sweep
---

# Migration Strategy — Employed (RBAC & tenancy)

The hiring-platform evolution adds three Alembic revisions (`003`–`005`) on top
of the existing `001_initial_schema` and `002_add_password_changed_at`.
Migrations are **append-only** (never edit an applied revision) and each new
revision provides a **reversible** `downgrade()`. `alembic upgrade head` runs as
the compose `migrate` service before backend/worker start. See
`docs/operations/alembic-policy.md` for the broader policy.

Sources: `backend/alembic/versions/003_rbac_and_tenancy.py`,
`004_migrate_admins.py`, `005_migrate_legacy_profiles_and_jobs.py`.

## `003_rbac_and_tenancy` (schema)

Revises `002_add_password_changed_at`. Adds the tenancy/RBAC schema:

- **New native enum types:** `verificationstate`, `platformrole`, `tenantrole`,
  `membershipstatus`, `applicationstatus`, `webhookevent` (and reuses the
  existing `market_key_enum`). Enum types are created/dropped explicitly so
  `add_column`/`create_table` do not attempt implicit `CREATE TYPE`.
- **New tables:** `companies`, `memberships`, `profile_versions`,
  `applications`, `audit_logs`, `webhook_endpoints`, `webhook_deliveries`.
- **`jobs`:** add `company_id` (nullable FK → `companies`, `SET NULL`),
  `verification_status`, `external_refs`, plus index `ix_jobs_company_id`.
- **`profiles`:** add `json_resume`, `verification_status`, `external_refs`.
- **`users`:** add `external_refs`.

`downgrade()` reverses the table/column/enum creations.

## `004_migrate_admins` (data, no schema change)

Revises `003`. Maps every `User` whose `roles` array contains the legacy value
`"admin"` to the `platform_super_admin` Platform_Role, which carries permissions
equivalent to the prior full-admin access (R6.1/R6.2). The `roles` list is
remapped in place (order-preserving, de-duplicated); **no account is deleted**,
so every administrator is preserved (R6.3). `downgrade()` restores the legacy
`"admin"` value (R6.4).

## `005_migrate_legacy_profiles_and_jobs` (data, no schema change)

Revises `004`. Three reversible conversions:

1. **Company profiles → companies.** Each `Profile` whose `type` is the legacy
   `Company` value becomes a `Company` owned by the profile's user, plus an
   `org_owner` / `active` `Membership` for that user (R23.1/R23.2). Created
   companies are tagged via `external_refs.migrated_from_profile` so the
   downgrade removes exactly the rows this migration created. Default market for
   converted companies is `mz`, verification status `unverified`.
2. **Anonymous jobs preserved.** Jobs with a null `company_id` are left
   untouched and remain legacy/anonymous jobs (R23.3); no jobs/profiles/users are
   ever deleted, preserving production data (R23.4).
3. **`status_history` → audit trail.** Each entry in a job's `status_history`
   JSONB array is backfilled into the append-only `audit_logs` trail in order
   (R22.4). Backfilled rows carry an `after._migration` marker so the downgrade
   deletes exactly them.

`downgrade()` uses the `external_refs.migrated_from_profile` and
`after._migration` markers to remove precisely the rows produced here.

## Verification

Migrations `003`–`005` are exercised by seeding a representative pre-migration
dataset, running `upgrade()` then `downgrade()`, and asserting conservation and
reversibility (design Properties 26–28). These tests run against a **real
Postgres** test database, since enum-type and JSONB behavior differs from SQLite.

```bash
# from backend/
alembic upgrade head      # 001 → 005
alembic downgrade -1      # step back one revision
```

See also: DATA_MODEL.md, RBAC_AND_TENANCY.md,
`docs/operations/alembic-policy.md`.
