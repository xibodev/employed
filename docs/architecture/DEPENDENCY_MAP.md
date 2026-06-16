---
last_verified: 2026-06-14T00:00:00Z
git_ref: working-tree (fix/quality-run-2026-06-10 lineage; uat baseline 00aa899)
verified_by: codebase-cartographer — FP-CARTO-007 doc refresh (2026-06-14)
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
| sentry-sdk[fastapi] | `init_sentry()` — DSN-gated; SDK kept on the planned Bugsink swap (Sentry-SDK compatible, DSN-only change) |
| pydantic-settings | `app/config.py` settings |

## Frontend (Node 20) — `frontend/package.json`

| Package | Version | Used for |
|---------|---------|----------|
| next | 15.0.0 | App Router, standalone output |
| react / react-dom | 19.0.0 | UI |
| next-intl | ^3.26.5 | hostname-driven i18n (en/pt/es) |
| @sentry/nextjs | ^9.0.0 | error tracking (DSN-gated); SDK kept on the planned Bugsink swap (DSN-only change) |
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

| Service | Integration point | Env (names only) | State (current → target) |
|---------|-------------------|------------------|--------------------------|
| Email relay — Resend → **AWS SES (planned)** | `app/services/email.py` — smtplib | `SMTP_HOST/PORT/USERNAME/PASSWORD`, `SMTP_USE_SSL/TLS`, `FROM_EMAIL` | **CURRENT:** Resend SMTP, live via the verified `xibodev.com` apex sender. **TARGET (planned):** AWS SES (eu-west-1 default), config-level swap (SMTP creds + sender domain, same backend Resend wraps). Sender → `noreply@employed.xibodev.com` once that domain is DKIM-verified on SES; until then fall back to `noreply@xibodev.com` (apex, on Resend) or mail bounces. Employed is on the priority SES bulk-verify list (`equilibria`/`kumbuka`/`nagare`/`employed`). **Status: pending SES domain verification.** Source: `docs/operations/INFRASTRUCTURE.md` (Email — transactional) |
| Google OAuth | `app/auth/oauth.py` | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | live (only provider); per-product GCP project `employed-uat-1779918377033` stays until next rotation, then cuts to shared `xibodev-com` (`docs/operations/INFRASTRUCTURE.md` OAuth) |
| Google reCAPTCHA v3 | `app/routers/jobs.py#_verify_recaptcha`; `ui/RecaptchaWidget` | `RECAPTCHA_SECRET_KEY` (fallback name `RECAPTCHA_V3_SECRET_KEY`), `NEXT_PUBLIC_RECAPTCHA_SITE_KEY`, `RECAPTCHA_MIN_SCORE` | live; action `submit_job` |
| Stripe | `app/payments/stripe_adapter.py`, `app/webhooks/stripe_webhook.py` | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PUBLISHABLE_KEY` | test keys (UAT) |
| M-Pesa / e-Mola | `app/payments/{mpesa,emola}_adapter.py`, `app/webhooks/mobile_money.py` | `MPESA_SIMULATOR`/`EMOLA_SIMULATOR`, `MPESA_WEBHOOK_SECRET`/`EMOLA_WEBHOOK_SECRET` | simulator mode (default) |
| Error tracking — Sentry SDK → **Bugsink on Box 0 (planned)** | `app/observability.py`; `frontend/sentry.*.config.ts` | `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `SENTRY_TRACES_SAMPLE_RATE` | **CURRENT:** Sentry SDK wired both ends but **no DSN set** (no-op / dormant). **TARGET (planned):** Bugsink self-hosted on **Box 0** (`https://errors.xibodev.com`, stack `xibodev-atlas/box0/`), the portfolio standard since 2026-06-11. Sentry-SDK compatible, so this is a **DSN-only swap** (code unchanged). When a DSN is set it MUST be a Bugsink DSN — projects `employed-api` (backend) + `employed-web`/`employed-uat` (frontend), team `xibodev`; never a new Sentry SaaS project (legacy org `nmtss` kept read-only). **Status: pending DSN provisioning.** Source: `docs/operations/INFRASTRUCTURE.md` (Error tracking) |
| Uptime monitoring — UptimeRobot → **Gatus on Box 0 (planned)** | external monitors on `/health` + frontend | n/a (monitor config external) | **CURRENT:** UptimeRobot (external) on `/health` + frontend. **TARGET (planned):** Gatus on Box 0 (portfolio standard since 2026-06-10; UptimeRobot retired). Not wired here yet. Source: `docs/operations/INFRASTRUCTURE.md` (Uptime monitoring) |

### Planned external-service migrations (target state, not yet in code)

These are **authoritative portfolio decisions** recorded as target/planned
state — the Employed source tree still uses Resend and the Sentry SDK
(no DSN), so neither swap is complete:

1. **Resend → AWS SES** (transactional email). SES eu-west-1 is the portfolio
   standard; same backend Resend wraps, so a config-level swap. Employed is on
   the priority bulk-verify list. Target sender `noreply@employed.xibodev.com`
   after DKIM verification, with `noreply@xibodev.com` (Resend apex) as the
   mandatory fallback until then. Status: pending SES domain verification.
2. **Sentry SDK → Bugsink on Box 0** (error tracking). Bugsink
   (`https://errors.xibodev.com`, Box 0, stack `xibodev-atlas/box0/`) is
   Sentry-SDK compatible — DSN-only swap. When provisioned the DSN must be a
   Bugsink project (`employed-api` backend, `employed-web`/`employed-uat`
   frontend, team `xibodev`); no new Sentry SaaS projects (`nmtss` read-only).
   Status: pending DSN provisioning.

Both decisions are sourced from `docs/operations/INFRASTRUCTURE.md`
(see `docs/operations/INFRASTRUCTURE.md` for the sender pattern). Per-product DSN/sender values
live in the product's `SERVICES.md`, never in this repo.

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
