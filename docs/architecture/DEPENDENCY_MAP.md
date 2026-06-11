---
last_verified: 2026-06-11T01:31:02Z
git_ref: fix/quality-run-2026-06-10 @ 5868453 (28 commits ahead of uat @ 00aa899)
verified_by: quality run 2026-06-10_120309 — codebase cartography
---

# Dependency Map — Employed

## Backend (Python 3.12) — pinned since EMP-021

Requirement sets are split by concern; **only the first three are baked into
the production image** (`backend/Dockerfile` builder stage merges them and
dedupes):

| File | In image | Contents |
|------|----------|----------|
| `backend/requirements.txt` | yes | sqlalchemy[asyncio] 2.0.49, alembic 1.18.4, psycopg2-binary 2.9.10, pydantic-settings 2.14.0, python-dotenv 1.0.0, email-validator 2.1.0, sentry-sdk[fastapi] 2.18.0 |
| `backend/requirements-api.txt` | yes | fastapi 0.135.2, uvicorn[standard] 0.42.0, python-jose[cryptography] 3.3.0, bcrypt 5.0.0, python-slugify 8.0.4, bleach 6.3.0, httpx 0.28.1, python-multipart 0.0.20 |
| `backend/requirements-payments.txt` | yes | stripe 7.11.0, arq 0.27.0, redis 5.0.1 |
| `backend/requirements-migration.txt` | no | pymongo/tqdm — legacy Mongo→Postgres one-shot tooling only |
| `backend/requirements-test.txt` | no | pytest et al. — CI/dev only |

Role of the load-bearing ones:

| Package | Used for |
|---------|----------|
| fastapi / uvicorn | HTTP app + ASGI server (`app/main.py`) |
| sqlalchemy / psycopg2 / alembic | ORM, Postgres driver, migrations |
| python-jose | JWT encode/decode (`app/auth/jwt.py`) |
| bcrypt | password hashing (`app/auth/passwords.py`) |
| bleach | HTML description sanitization (`app/services/html_sanitizer.py`) |
| httpx | outbound calls (Google OAuth token/userinfo, reCAPTCHA verify) |
| stripe | Stripe adapter (`app/payments/stripe_adapter.py`) |
| arq / redis | worker queue + cron; rate limiting, lockout, JTI revocation, replay cache |
| sentry-sdk[fastapi] | `init_sentry()` — DSN-gated |
| pydantic-settings | `app/config.py` settings |

## Frontend (Node 20) — `frontend/package.json`

| Package | Version | Used for |
|---------|---------|----------|
| next | 15.0.0 | App Router, standalone output |
| react / react-dom | 19.0.0 | UI |
| next-intl | ^3.26.5 | hostname-driven i18n (en/pt/es) |
| @sentry/nextjs | ^9.0.0 | error tracking (DSN-gated) |
| @tiptap/react + starter-kit | ^2.10.4 | rich-text job description editor |
| react-google-recaptcha-v3 | ^1.11.0 | reCAPTCHA widget on anonymous job post |
| typescript | ^5.7.2 (dev) | typecheck (`tsc --noEmit`) |
| tailwindcss + @tailwindcss/postcss | ^4.0.0 (dev) | styling |
| eslint + @typescript-eslint/* | ^9 / ^8 (dev) | lint (`--max-warnings 0`) |

Install note: `npm ci --legacy-peer-deps` (React 19 peer-dep friction) —
used in Dockerfile and CI.

## E2E tooling — `tests/e2e/package.json`

Playwright journey suites (52 tests across visitor/seeker/employer/admin/
multi-user + smoke), locale-aware assertions via `tests/e2e/i18n.js`
(TD-001). Run locally against the compose test stack; not part of CI.

## Infrastructure images (`deploy/docker-compose*.yml`)

| Image | Role |
|-------|------|
| `postgres:16-alpine` | primary datastore (volume `postgres_data`) |
| `redis:7-alpine` | queue/limits/revocation/replay (no persistence: `--save "" --appendonly no`) |
| `ghcr.io/mekjr1/employed-api:uat` | backend + worker + migrate (one image, three services) |
| `ghcr.io/mekjr1/employed-frontend:uat` | frontend |
| `python:3.12-slim` / `node:20-alpine` | build bases |
| MailHog (test overlay only) | SMTP capture at 3310/3311 |

## External services

| Service | Integration point | Env (names only) | State |
|---------|-------------------|------------------|-------|
| Resend (SMTP relay) | `app/services/email.py` — smtplib | `SMTP_HOST/PORT/USERNAME/PASSWORD`, `SMTP_USE_SSL/TLS`, `FROM_EMAIL` | live via verified `xibodev.com` sender |
| Google OAuth | `app/auth/oauth.py` | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | live (only provider) |
| Google reCAPTCHA v3 | `app/routers/jobs.py#_verify_recaptcha`; `ui/RecaptchaWidget` | `RECAPTCHA_SECRET_KEY` (fallback name `RECAPTCHA_V3_SECRET_KEY`), `NEXT_PUBLIC_RECAPTCHA_SITE_KEY`, `RECAPTCHA_MIN_SCORE` | live; action `submit_job` |
| Stripe | `app/payments/stripe_adapter.py`, `app/webhooks/stripe_webhook.py` | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PUBLISHABLE_KEY` | test keys (UAT) |
| M-Pesa / e-Mola | `app/payments/{mpesa,emola}_adapter.py`, `app/webhooks/mobile_money.py` | `MPESA_SIMULATOR`/`EMOLA_SIMULATOR`, `MPESA_WEBHOOK_SECRET`/`EMOLA_WEBHOOK_SECRET` | simulator mode (default) |
| Sentry | `app/observability.py`; `frontend/sentry.*.config.ts` | `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `SENTRY_TRACES_SAMPLE_RATE` | wired, not provisioned |
| UptimeRobot | external monitors on `/health` + frontend | n/a (monitor config external) | live |

## Internal dependency edges (module level)

```
frontend src/lib/api.ts ──HTTP──► backend routers (always with X-Forwarded-Host)
routers ──► auth.dependencies ──► auth.jwt / revocation (Redis)
routers ──► middleware.market (market dep) / middleware.rate_limit
routers/jobs ──► services.email, services.html_sanitizer
routers/payments ──► payments registry ──► {stripe,mpesa,emola}_adapter ──► settlement
webhooks ──► replay_cache (Redis) ──► settlement ──► models
workers.tasks ──► payments.settlement (shared session/model helpers)
public_api ──► routers.jobs internals (_apply_filters, _job_to_read)
```

Notable coupling: `public_api.py` imports private helpers from
`routers/jobs.py`, and `admin.py` imports `_job_model`/`_job_to_read` inside
the handler — refactors of jobs router internals ripple into both.

## CI dependency notes (`.github/workflows/ci.yml`)

CI merges **all** `backend/requirements*.txt` (including migration/test
sets) into `requirements-ci.txt` — intentionally broader than the production
image, which excludes migration/test deps (EMP-021). Backend tests run
against real Postgres 16 + Redis 7 service containers.
