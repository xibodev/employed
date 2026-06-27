---
last_verified: 2026-06-27T00:00:00Z
git_ref: master
verified_by: codebase-cartographer — FP-CARTO-007 doc refresh (2026-06-14)
---

# Data Model — Employed

PostgreSQL 16, SQLAlchemy 2 declarative models, Alembic migrations.
Sources: `backend/app/models/*.py`, `backend/app/database.py`,
`backend/alembic/versions/001_initial_schema.py`,
`backend/alembic/versions/002_add_password_changed_at.py`,
`backend/alembic/versions/003_rbac_and_tenancy.py`,
`004_migrate_admins.py`, `005_migrate_legacy_profiles_and_jobs.py`.

> **Hiring-platform evolution (multi-tenant-hiring-platform spec).** Migration
> `003` adds the tenancy/RBAC tables — `companies`, `memberships`,
> `profile_versions`, `applications`, `audit_logs`, `webhook_endpoints`,
> `webhook_deliveries` — and extends `jobs`, `profiles`, and `users` with
> `verification_status` and/or `external_refs`. See the new tables below and the
> companion docs: RBAC_AND_TENANCY.md, VERIFICATION_AND_TRUST.md,
> INTEGRATION_AND_EXPORT.md, MIGRATION_STRATEGY.md.

## Conventions (`backend/app/database.py`)

Every table inherits from `Base`:

- `id UUID PRIMARY KEY DEFAULT gen_random_uuid()` (pgcrypto)
- `created_at` / `updated_at` `timestamptz NOT NULL` (server default `now()`,
  also maintained by ORM events)
- Constraint naming convention (`ix_/uq_/ck_/fk_/pk_`) on shared `MetaData`.

Extensions enabled in migration 001: `pg_trgm`, `pgcrypto`.

## Entity-relationship summary

```
users 1──* jobs 1──* payment_intents *──1 users
users 1──1 profiles
jobs  1──* job_reports *──0..1 users (reporter)
                       *──0..1 users (resolver)

# hiring-platform evolution (migration 003)
users    1──* memberships *──1 companies
companies 0..1──* jobs              (nullable company_id: null ⇒ legacy/anonymous)
profiles 1──* profile_versions
jobs     1──* applications *──0..1 users (candidate)
                           *──0..1 profile_versions (resume_version)
companies 0..1──* webhook_endpoints 1──* webhook_deliveries
(audit_logs: append-only, polymorphic target_type/target_id)
```

## users (`backend/app/models/user.py`)

| Column | Type | Notes |
|--------|------|-------|
| `email` | varchar(320) UNIQUE NOT NULL | normalized to lowercase on write (EMP-005) |
| `email_verified` | boolean NOT NULL default false | |
| `username` | varchar(64) UNIQUE NULL | |
| `password_hash` | varchar(128) NULL | bcrypt; NULL for OAuth-only accounts |
| `display_name` | varchar(128) NULL | |
| `roles` | text[] NOT NULL default `{}` | platform roles live here. Legacy `admin` is remapped to `platform_super_admin` by migration 004; recognized values: `platform_super_admin`, `platform_moderator`, `platform_support` (see RBAC_AND_TENANCY.md) |
| `oauth_providers` | jsonb NOT NULL default `{}` | provider → claims map; JSONB-containment lookups |
| `external_refs` | jsonb NOT NULL default `{}` | external system id map (migration 003); JSONB write, never a migration (R19) |
| `is_developer` | boolean NOT NULL default false | |
| `deletion_requested_at` / `deletion_scheduled_for` | timestamptz NULL | 30-day GDPR-style deletion window; worker hard-deletes |
| `password_changed_at` | timestamptz NULL | added in migration 002; invalidates pre-change tokens |

Verification semantics: a row with neither email-credential nor OAuth
evidence reads as **not** verified (EMP-022,
`backend/app/auth/dependencies.py#is_email_verified`).

## jobs (`backend/app/models/job.py`)

| Column | Type | Notes |
|--------|------|-------|
| `user_id` | UUID FK → users.id ON DELETE SET NULL, NULL | anonymous posts allowed (reCAPTCHA-gated) |
| `title` | varchar(256) NOT NULL | |
| `company` | varchar(256) NULL | |
| `country` | `country_enum` NOT NULL (`Mexico`, `Mozambique`) | stamped from active market at creation |
| `location`, `url`, `contact`, `apply_whatsapp` | varchar | `contact` NOT NULL |
| `job_type` | `job_type_enum` NOT NULL | Full Time, Part Time, Contract, Temporary, Internship, Freelance, Remote, Volunteer, Other |
| `remote` | boolean NOT NULL default false | |
| `description` | text NOT NULL; `html_description` text NULL (bleach-sanitized) | |
| `salary_min`/`salary_max` | integer NULL | |
| `salary_currency` | `salary_currency_enum` NULL (MXN, MZN, USD) | |
| `salary_period` | `salary_period_enum` NULL (hour/day/week/month/year) | |
| `status` | `job_status_enum` NOT NULL default `pending` | pending, active, flagged, inactive, filled |
| `featured_through` | timestamptz NULL | featured while >= now |
| `featured_charge_history` | jsonb list NOT NULL default `[]` | appended at settlement |
| `status_history` | jsonb list NOT NULL default `[]` | audit trail (capped at 100 entries); expiry recorded with reason `expired` (EMP-017) |
| `published_at`, `expired_at` | timestamptz NULL | |
| `recaptcha_score` | float NULL | |
| `company_id` | UUID FK → companies.id ON DELETE SET NULL, NULL | migration 003; null ⇒ legacy/anonymous job (R4.3). `posted_by` reference remains `user_id` |
| `verification_status` | `verificationstate` NOT NULL default `unverified` | publication verification state (migration 003) |
| `external_refs` | jsonb NOT NULL default `{}` | external system id map (migration 003) |

Indexes (ORM `__table_args__` mirrors migration 001 exactly — EMP-009):

- `idx_jobs_status_country_created (status, country, created_at DESC)` — primary listing query
- `idx_jobs_user_id (user_id)`
- `idx_jobs_featured (featured_through) WHERE featured_through IS NOT NULL`
- `idx_jobs_title_trgm` / `idx_jobs_company_trgm` — GIN `gin_trgm_ops`, back the SQL ILIKE search (EMP-010)
- `ix_jobs_company_id (company_id)` — tenant-scoped listing (migration 003)

## profiles (`backend/app/models/profile.py`)

| Column | Type | Notes |
|--------|------|-------|
| `user_id` | UUID FK → users.id ON DELETE CASCADE, UNIQUE NOT NULL | 1:1 with users |
| `name`, `title` | varchar(128) NOT NULL | |
| `type` | `profile_type_enum` NOT NULL (Individual, Company) | |
| `location` | varchar(256) NOT NULL; `description` text NOT NULL | |
| `available_for_hire` | boolean NOT NULL default false | |
| `interested_in` | text[] NOT NULL default `{}` | |
| `contact`, `url`, `resume_url`, `github_url`, `linkedin_url`, `stackoverflow_url`, `custom_image_url`, `user_name` | varchar NULL | |
| `status` | `profile_status_enum` NOT NULL default `pending` (pending, active, flagged) | |
| `random_sorter` | float NULL | randomized listing order |
| `json_resume` | jsonb NULL | live JSON Resume working copy (migration 003, R13.5) |
| `verification_status` | `verificationstate` NOT NULL default `unverified` | profile identity verification (migration 003) |
| `external_refs` | jsonb NOT NULL default `{}` | external system id map (migration 003) |

## payment_intents (`backend/app/models/payment_intent.py`)

| Column | Type | Notes |
|--------|------|-------|
| `job_id` | UUID FK → jobs.id ON DELETE CASCADE NOT NULL | |
| `user_id` | UUID FK → users.id ON DELETE CASCADE NOT NULL | |
| `market_key` | `market_key_enum` NOT NULL (mx, mz) | |
| `provider_key` | `payment_provider_key_enum` NOT NULL (stripe, mpesa, emola) | |
| `provider_ref` | varchar(256) NULL | provider's reference; webhook lookups |
| `status` | `payment_status_enum` NOT NULL default `pending` | pending, awaiting_user, completed, failed, cancelled, expired; terminal = completed/failed/cancelled/expired |
| `amount` | integer NOT NULL (minor units); `currency` char(3) NOT NULL | MX$999 = 99900 mxn; MZN 2,500 = 250000 mzn |
| `payer_msisdn` | varchar(4) NULL — truncated; `payer_msisdn_hash` varchar(64) NULL — salted hash (`IP_SALT`) | privacy by design |
| `extended_through` | timestamptz NULL | featured window granted |
| `failure_reason` | varchar(256) NULL | |
| `simulator` | boolean NOT NULL default false | true for simulator-mode mobile money |
| `meta` | jsonb NOT NULL default `{}` | |
| `settled_at` | timestamptz NULL | |

Indexes (mirrors migration 001 — EMP-009):

- `idx_payment_intents_provider_ref (provider_ref) WHERE provider_ref IS NOT NULL`
- `idx_payment_intents_job_user (job_id, user_id)`

## job_reports (`backend/app/models/job_report.py`)

| Column | Type | Notes |
|--------|------|-------|
| `job_id` | UUID FK → jobs.id ON DELETE CASCADE NOT NULL | |
| `reason` | `report_reason_enum` NOT NULL | spam, scam, discriminatory, wrong_country, expired_or_filled, duplicate |
| `details` | varchar(2000) NULL | |
| `reporter_ip_hash` | varchar(32) NULL | salted hash, anonymous reports |
| `reporter_user_id` | UUID FK → users.id ON DELETE SET NULL NULL | |
| `resolution` | `report_resolution_enum` NOT NULL default `pending` | pending, reviewed, dismissed, job_removed |
| `resolved_by` | UUID FK → users.id ON DELETE SET NULL NULL; `resolved_at` timestamptz NULL | |

Index (migration 001): `idx_job_reports_resolution (resolution, created_at DESC)`.

## Hiring-platform tables (migration 003)

The following tables back multi-tenancy, RBAC, verification, version-controlled
profiles, applications, audit, and webhooks. See RBAC_AND_TENANCY.md,
VERIFICATION_AND_TRUST.md, and INTEGRATION_AND_EXPORT.md for behavior.

### companies (`backend/app/models/company.py`)

| Column | Type | Notes |
|--------|------|-------|
| `name` | varchar(256) NOT NULL | |
| `slug` | varchar(256) NOT NULL | unique within `market` |
| `market` | `market_key_enum` NOT NULL (mx, mz) | single market per company (Open Decision 2) |
| `description` | text NULL | |
| `logo_url`, `website` | varchar(2048) NULL | |
| `verification_status` | `verificationstate` NOT NULL default `unverified` | |
| `created_by` | UUID FK → users.id ON DELETE SET NULL, NULL | creating user (R1.4) |
| `verified_email_domains` | jsonb list NOT NULL default `[]` | verified domains (R3.1, R9.5) |
| `trust_badges` | jsonb list NOT NULL default `[]` | derived, reconciled by the trust service |
| `external_refs` | jsonb NOT NULL default `{}` | |

Constraint: `uq_companies_market_slug (market, slug)`.

### memberships (`backend/app/models/membership.py`)

| Column | Type | Notes |
|--------|------|-------|
| `user_id` | UUID FK → users.id ON DELETE CASCADE NOT NULL | |
| `company_id` | UUID FK → companies.id ON DELETE CASCADE NOT NULL | |
| `role` | `tenantrole` NOT NULL (org_owner, org_admin, recruiter, member) | |
| `status` | `membershipstatus` NOT NULL (invited, active, suspended) | only `active` grants tenant permissions |
| `invited_by` | UUID FK → users.id ON DELETE SET NULL, NULL | |

Constraint: `uq_memberships_user_company (user_id, company_id)` — one membership
per user/company pair. No company FK on `users`; a user may hold memberships in
multiple companies.

### profile_versions (`backend/app/models/profile_version.py`)

Append-only, immutable snapshots (no `updated_at`; `before_update` guard raises).

| Column | Type | Notes |
|--------|------|-------|
| `profile_id` | UUID FK → profiles.id ON DELETE CASCADE NOT NULL | |
| `user_id` | UUID FK → users.id ON DELETE CASCADE NOT NULL | denormalized owner |
| `version_number` | integer NOT NULL | monotonic per profile |
| `json_resume` | jsonb NOT NULL | immutable snapshot |

Constraint: `uq_profile_versions_profile_version (profile_id, version_number)`.

### applications (`backend/app/models/application.py`)

| Column | Type | Notes |
|--------|------|-------|
| `job_id` | UUID FK → jobs.id ON DELETE CASCADE NOT NULL | |
| `candidate_user_id` | UUID FK → users.id ON DELETE SET NULL, NULL | candidate user ref (R16.2) |
| `candidate_snapshot` | jsonb NULL | profile snapshot alt. to user ref |
| `company_id` | UUID FK → companies.id ON DELETE SET NULL, NULL | |
| `status` | `applicationstatus` NOT NULL default `applied` | applied, reviewed, shortlisted, rejected, hired |
| `resume_version_id` | UUID FK → profile_versions.id ON DELETE SET NULL, NULL | |
| `cover_note` | text NULL | |
| `source` | varchar(64) NOT NULL default `platform` | e.g. `platform`, `email` |
| `external_refs` | jsonb NOT NULL default `{}` | |

Check constraint `candidate_present`: `candidate_user_id IS NOT NULL OR
candidate_snapshot IS NOT NULL`.

### audit_logs (`backend/app/models/audit_log.py`)

Append-only (no `updated_at`; `before_update` guard raises). `created_at` is the
timestamp.

| Column | Type | Notes |
|--------|------|-------|
| `actor_id` | UUID FK → users.id ON DELETE SET NULL, NULL | null + `actor_label` for system actors |
| `actor_label` | varchar(128) NULL | e.g. `worker:domain_verify` |
| `action` | varchar(128) NOT NULL | e.g. `verification.transition`, `application.status_changed`, `job.block` |
| `target_type` | varchar(64) NOT NULL | entity type |
| `target_id` | UUID NOT NULL | entity id |
| `before`, `after` | jsonb NULL | prior / new state |

### webhook_endpoints (`backend/app/models/webhook.py`)

| Column | Type | Notes |
|--------|------|-------|
| `company_id` | UUID FK → companies.id ON DELETE CASCADE, NULL | null ⇒ platform-level endpoint |
| `url` | varchar(2048) NOT NULL | |
| `secret` | varchar(256) NOT NULL | HMAC signing key; never returned in API responses |
| `events` | jsonb list NOT NULL default `[]` | subscribed `webhookevent` values |
| `active` | boolean NOT NULL default true | soft-delete on deactivate |

### webhook_deliveries (`backend/app/models/webhook.py`)

| Column | Type | Notes |
|--------|------|-------|
| `endpoint_id` | UUID FK → webhook_endpoints.id ON DELETE CASCADE NOT NULL | |
| `event` | `webhookevent` NOT NULL | job.published, application.created, application.status_changed |
| `payload` | jsonb NOT NULL default `{}` | |
| `status` | varchar(32) NOT NULL default `pending` | pending → delivered / failed |
| `attempts` | integer NOT NULL default 0 | bounded backoff retries (cap 10) |
| `next_attempt_at` | timestamptz NULL | next retry time |
| `last_error` | text NULL | last delivery error (truncated) |

## Enums (`backend/app/models/enums.py`)

Native PostgreSQL enums created via `pg_enum()` with `values_callable`
(stores the human-readable values, e.g. `"Full Time"`, `"Mexico"`).
`OAuthProvider` (google/facebook/github/twitter) exists in code but only
google is wired.

Enums added by migration 003 (stored as their lowercase value strings):
`verificationstate` (unverified, pending, verified, rejected, revoked, flagged),
`platformrole` (platform_super_admin, platform_moderator, platform_support),
`tenantrole` (org_owner, org_admin, recruiter, member),
`membershipstatus` (invited, active, suspended),
`applicationstatus` (applied, reviewed, shortlisted, rejected, hired),
`webhookevent` (job.published, application.created, application.status_changed).

## Redis keyspace (not relational, but stateful)

| Key pattern | Writer | Purpose |
|-------------|--------|---------|
| `ratelimit:<scope>:<ip>` | `app/middleware/rate_limit.py` | fixed-window counters (TTL = window) |
| lockout keys (email+IP) | `app/routers/auth.py` | login lockout counters |
| revoked JTI keys | `app/auth/revocation.py` | refresh-token revocation (TTL = remaining token life) |
| `replay:<namespace>:<event-key>` | `app/webhooks/replay_cache.py` | webhook replay dedupe (TTL 300 s) |
| arq queue keys | arq | background job queue + cron state |

All Redis-backed features degrade to in-process fallbacks when `REDIS_URL`
is unset (dev/tests) — single-process only.

## Migration policy

Five migrations to date (`001`–`005`); `alembic upgrade head` runs as the
compose `migrate` service before backend/worker start
(`deploy/docker-compose*.yml`). Migrations `003`–`005` add the hiring-platform
schema and reversible data conversions (see MIGRATION_STRATEGY.md). ORM index
declarations must stay name-identical to migrations so autogenerate stays clean
(EMP-009). See `docs/operations/alembic-policy.md`.
