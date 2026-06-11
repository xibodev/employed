---
last_verified: 2026-06-11T01:31:02Z
git_ref: fix/quality-run-2026-06-10 @ 5868453 (28 commits ahead of uat @ 00aa899)
verified_by: quality run 2026-06-10_120309 — codebase cartography
---

# Repo Map — Employed

Monorepo for the Employed job board (markets MZ/MX selected by hostname,
locales en/pt/es). Two deployable surfaces (FastAPI backend, Next.js
frontend) plus a deploy/compose layer, all in one repo.

## Top-level layout

| Path | Category | Purpose | Key sources |
|------|----------|---------|-------------|
| `backend/` | source (API) | FastAPI app: routers, models, workers, payments, webhooks, Alembic migrations, pytest suite | `backend/app/main.py`, `backend/alembic/` |
| `frontend/` | source (web) | Next.js 15 App Router frontend (React 19, TypeScript, Tailwind 4, next-intl) | `frontend/src/app/`, `frontend/middleware.ts` |
| `deploy/` | deploy config | Compose files (base/dev/test/prod), nginx reference config, `.env.example` schema | `deploy/docker-compose*.yml`, `deploy/.env.example` |
| `.github/workflows/` | CI/CD | `ci.yml` (lint+test+build), `deploy-uat.yml` (build/push/SSH-deploy to Box 3), `init-server.yml` (one-time box init) | `.github/workflows/*.yml` |
| `docs/` | docs | API reference, operations runbooks, ADRs (`docs/decisions/`), this architecture bundle (`docs/architecture/`) | `docs/` |
| `tests/` | tests (E2E) | Playwright journey suites (visitor/seeker/employer/admin/multi-user) + smoke; own `package.json` | `tests/e2e/*.spec.js`, `tests/e2e/playwright.config.js` |
| `quality/` | test data | Personas, journeys, external-services inventory used by quality runs | `quality/*.json` |
| `scripts/` | tooling | Lighthouse mobile audit, brand PNG regeneration | `scripts/*.mjs`, `scripts/*.js` |
| `brand/`, `design/`, `public/` | assets | Brand identity (logos, colors, voice), rebrand previews, shared static assets | `brand/README.md` |
| `.quality-run/` | run artefacts | Quality-run inputs/outputs (not product code) | `.quality-run/results/` |
| `CLAUDE.md`, `AGENTS.md`*, `README.md`, `DEPLOY.md`, `SERVICES.md` | docs | Assistant rules, deployment source of truth, product/live-state notes | repo root |

`node_modules/` at the repo root is an untracked local artifact (zero tracked
files under it — `git ls-files`); the real dependency roots are
`frontend/package.json` and `tests/e2e/package.json`.

## Backend (`backend/`)

| Path | Purpose |
|------|---------|
| `app/main.py` | App factory: middleware stack, router wiring, `/health` (GET+HEAD), exception handlers |
| `app/config.py` | Pydantic Settings — every env var the API reads (see CONFIG_AND_SECRETS_MAP.md) |
| `app/database.py` | SQLAlchemy engine/session, declarative `Base` (UUID PK, created/updated timestamps) |
| `app/logging_config.py` | Structured logging + request-id context |
| `app/observability.py` | `init_sentry()` — no-op unless `SENTRY_DSN` set |
| `app/middleware/market.py` | `MarketMiddleware` — market from `X-Forwarded-Host` (first value) falling back to `Host` (EMP-001) |
| `app/middleware/rate_limit.py` | Redis fixed-window rate limiter with in-process fallback; trusted-proxy client-IP derivation (EMP-007/020) |
| `app/auth/` | `jwt.py` (HS256 access/refresh tokens), `dependencies.py` (`get_current_user`, `require_admin`, …), `oauth.py` (Google), `passwords.py` (bcrypt), `revocation.py` (Redis JTI revocation) |
| `app/routers/` | `auth`, `jobs`, `profiles`, `payments`, `reports`, `admin`, `users`, `public_api` (see API_MAP.md) |
| `app/models/` | `user`, `job`, `profile`, `payment_intent`, `job_report`, `enums` (see DATA_MODEL.md) |
| `app/schemas/` | Pydantic request/response models mirroring the routers |
| `app/services/` | `email.py` (SMTP transactional mail), `market.py` (market registry), `html_sanitizer.py` (bleach), `model_utils.py` |
| `app/payments/` | Provider adapters: `stripe_adapter` (live), `mpesa_adapter` + `emola_adapter` (simulator-by-default), `settlement.py`, registry in `__init__.py` |
| `app/webhooks/` | `stripe_webhook.py`, `mobile_money.py` (HMAC-SHA256 signature + mandatory timestamp), `replay_cache.py` (Redis dedupe, EMP-019) |
| `app/workers/` | arq worker: `config.py` (`WorkerSettings`), `cron.py` (job expiry, account deletion), `tasks.py` |
| `alembic/versions/` | `001_initial_schema.py`, `002_add_password_changed_at.py` |
| `tests/` | 13 pytest modules, 134 tests (83 baseline + 51 regression tests from the 2026-06-10 fix run) |
| `requirements*.txt` | Pinned dep sets: `requirements.txt` (core), `-api`, `-payments` (runtime, baked into image); `-migration`, `-test` (excluded from image since EMP-021) |
| `scripts/` | `backup-db.sh`, `create-uptimerobot-monitors.sh`, `migrate_mongo_to_postgres.py` (legacy one-shot) |
| `Dockerfile` | Two-stage python:3.12-slim; installs only the three runtime requirement sets (EMP-021); uvicorn on :8000 |

## Frontend (`frontend/`)

| Path | Purpose |
|------|---------|
| `src/app/` | App Router pages (see ROUTE_MAP.md) incl. `robots.ts`, `sitemap.ts`, `api/health/route.ts` |
| `middleware.ts` | Auth/admin route gating via `employed_token`/`employed_is_admin` cookies; sets `x-next-intl-locale` from hostname |
| `src/i18n/request.ts` | next-intl locale resolution: `mx.*` → `es`, everything else → `pt` |
| `messages/{en,pt,es}.json` | Locale catalogs (263 keys each, kept in sync) |
| `src/lib/` | `api.ts` (fetch client, sends `X-Forwarded-Host`), `market.ts` (markets derived from `NEXT_PUBLIC_APP_URL`), `runtime-config.ts` (`window.__ENV` runtime config, EMP-012), `seo.ts`, `types.ts`, `constants.ts`, `utils.ts` |
| `src/contexts/AuthContext.tsx` | Session state: access token in localStorage + non-httpOnly cookie; refresh token in memory + httpOnly cookie (EMP-006) |
| `src/hooks/` | `useAuth`, `useMarket` |
| `src/components/` | `account/`, `admin/`, `auth/`, `dashboard/`, `jobs/`, `layout/` (incl. `RuntimeEnvScript`), `ui/` (incl. `RecaptchaWidget`, `RichTextEditor`) |
| `sentry.{client,edge,server}.config.ts`, `instrumentation.ts` | Sentry wiring (DSN-gated) |
| `next.config.ts` | `output: "standalone"`, security headers + CSP, next-intl plugin |
| `Dockerfile` | Three-stage node:20-alpine standalone build; `NEXT_PUBLIC_*` build args remain as fallbacks, runtime values win via `window.__ENV` |

## Entry points

| Surface | Entry | Command |
|---------|-------|---------|
| API | `backend/app/main.py` → `app = create_app()` | `uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| Worker | `backend/app/workers/config.py` → `WorkerSettings` | `arq app.workers.config.WorkerSettings` |
| Migrations | `backend/alembic.ini` | `alembic upgrade head` (compose `migrate` service) |
| Frontend | `frontend/server.js` (standalone build output) | `node server.js` (port 3000) |

## Don't touch casually

- `backend/alembic/versions/` — migration history; ORM `__table_args__` index
  names are deliberately mirrored to these files (EMP-009).
- `deploy/docker-compose.prod.yml` — copied verbatim to Box 3 as the live
  compose file by `deploy-uat.yml`.
- `frontend/src/lib/market.ts` / `src/app/robots.ts` / `src/app/sitemap.ts` —
  domain derivation contract: no hardcoded domains (EMP-013/024, AI-OPS Rule 2).
- `docs/decisions/001–004` — historical Meteor-era ADRs, superseded; keep as
  archive context only.

## Historical / archive material

`MIGRATION-PLAN.md`, `docs/meteor-3-package-audit.md`,
`docs/decisions/001–004`, `backend/scripts/migrate_mongo_to_postgres.py` and
`docs/archive/` document the retired Meteor/Mongo implementation. The live
stack is FastAPI + Next.js + PostgreSQL/Redis.
