---
last_verified: 2026-06-11T01:31:02Z
git_ref: fix/quality-run-2026-06-10 @ 5868453 (28 commits ahead of uat @ 00aa899)
verified_by: quality run 2026-06-10_120309 — codebase cartography
---

# Data Model — Employed

PostgreSQL 16, SQLAlchemy 2 declarative models, Alembic migrations.
Sources: `backend/app/models/*.py`, `backend/app/database.py`,
`backend/alembic/versions/001_initial_schema.py`,
`backend/alembic/versions/002_add_password_changed_at.py`.

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
```

## users (`backend/app/models/user.py`)

| Column | Type | Notes |
|--------|------|-------|
| `email` | varchar(320) UNIQUE NOT NULL | normalized to lowercase on write (EMP-005) |
| `email_verified` | boolean NOT NULL default false | |
| `username` | varchar(64) UNIQUE NULL | |
| `password_hash` | varchar(128) NULL | bcrypt; NULL for OAuth-only accounts |
| `display_name` | varchar(128) NULL | |
| `roles` | text[] NOT NULL default `{}` | only role in use: `admin` |
| `oauth_providers` | jsonb NOT NULL default `{}` | provider → claims map; JSONB-containment lookups |
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

Indexes (ORM `__table_args__` mirrors migration 001 exactly — EMP-009):

- `idx_jobs_status_country_created (status, country, created_at DESC)` — primary listing query
- `idx_jobs_user_id (user_id)`
- `idx_jobs_featured (featured_through) WHERE featured_through IS NOT NULL`
- `idx_jobs_title_trgm` / `idx_jobs_company_trgm` — GIN `gin_trgm_ops`, back the SQL ILIKE search (EMP-010)

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

## Enums (`backend/app/models/enums.py`)

Native PostgreSQL enums created via `pg_enum()` with `values_callable`
(stores the human-readable values, e.g. `"Full Time"`, `"Mexico"`).
`OAuthProvider` (google/facebook/github/twitter) exists in code but only
google is wired.

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

Two migrations to date; `alembic upgrade head` runs as the compose `migrate`
service before backend/worker start (`deploy/docker-compose*.yml`). ORM
index declarations must stay name-identical to migrations so autogenerate
stays clean (EMP-009). See `docs/operations/alembic-policy.md`.
