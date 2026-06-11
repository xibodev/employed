---
last_verified: 2026-06-11T04:50:00Z
git_ref: fix/quality-run-2026-06-10 (uat baseline 00aa899)
verified_by: fix-executor follow-up pass, quality run 2026-06-10_120309
---

# Settings Reference

> Environment variable reference for the FastAPI backend and Next.js frontend.
> On Box 3 all values are injected at runtime via `/opt/employed/.env`
> (upserted by `deploy-uat.yml`). Local template: `deploy/.env.example`.
> Var × consumer map: `docs/architecture/CONFIG_AND_SECRETS_MAP.md`.
>
> Principle (AI-OPS Rule 11): mutable values are runtime config — a change is
> a restart, not a rebuild. The backend reads settings through
> `backend/app/config.py` (pydantic-settings, case-insensitive, `.env`
> support). Frontend `NEXT_PUBLIC_API_URL` / `NEXT_PUBLIC_RECAPTCHA_SITE_KEY`
> are served per-request via `window.__ENV` (`RuntimeEnvScript`) — the Docker
> build args remain only as fallbacks.
>
> **Deploy gap (BL-001): resolved on branch, pending merge (2026-06-11).**
> `deploy-uat.yml` now upserts `FRONTEND_BASE_URL`, `NEXT_PUBLIC_APP_URL`,
> exact-origin `CORS_ORIGINS`, `ENVIRONMENT=uat`, `SENTRY_DSN` and
> `SENTRY_ENVIRONMENT=uat` — applied on the first post-merge deploy
> (see `docs/architecture/DEPLOYMENT_TOPOLOGY.md`).

---

## Core

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SECRET_KEY` (alias `JWT_SECRET_KEY`) | **Yes (non-dev)** | dev/test only: `development-only-secret-key` | JWT signing key. Outside development/testing, startup fails without it (`ensure_jwt_secret_configured`). |
| `ENVIRONMENT` | No | `development` | Gates HSTS, secure cookies, the dev secret fallback, and the reCAPTCHA dev bypass. UAT sets `uat` — upserted by the deploy workflow as of BL-001 (branch, pending merge). |
| `DEBUG` | No | `false` | Dev-mode detection. Never `true` in production. |
| `IP_SALT` | **Yes** | unset | Salt for hashing reporter IPs and payer MSISDNs before storage/logging. |
| `LOG_LEVEL` | No | `INFO` | Python logging level. |

---

## Database & Redis

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | **Yes** | `postgresql+psycopg2://postgres:postgres@localhost:5432/employed` | Sync SQLAlchemy DSN; the async variant is derived automatically (`postgresql+asyncpg://`). |
| `ALEMBIC_DATABASE_URL` | No | falls back to `DATABASE_URL` | Migration-specific DSN override. |
| `DATABASE_POOL_SIZE` / `DATABASE_MAX_OVERFLOW` / `DATABASE_POOL_TIMEOUT` / `DATABASE_POOL_RECYCLE` | No | 5 / 10 / 30 / 1800 | Engine pool tuning. |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Yes (compose) | — | Consumed by the `postgres` compose service only. |
| `REDIS_URL` | No | unset | Redis DSN (`redis://redis:6379/0`). Used for the arq job queue, rate limiting, login lockout, refresh-JTI revocation, webhook replay dedupe, and the `/health` component check. Without it those features degrade to in-process fallbacks. |

---

## Auth / JWT

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `JWT_ALGORITHM` | No | `HS256` | HMAC algorithm for JWT signing. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `30` | Access token TTL in minutes. |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | `7` | Refresh token TTL in days (also the refresh-cookie Max-Age). |

---

## Network trust & abuse protection

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TRUSTED_PROXY_IPS` | No | loopback + RFC1918 CIDRs | Comma-separated IPs/CIDRs whose `X-Forwarded-For` is trusted for client-IP resolution (rate limiting / lockout). |
| `CORS_ORIGINS` (alias `BACKEND_CORS_ORIGINS`) | **Yes outside dev** | `*` in development, empty otherwise | Exact frontend origins. Credentialed (cookie) auth cannot use the wildcard — must be set per deployed env. |

---

## reCAPTCHA v3 (anonymous job posting)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `RECAPTCHA_SECRET_KEY` (fallback name `RECAPTCHA_V3_SECRET_KEY`) | Yes for anonymous posting | unset | Server-side verify secret. **If absent, anonymous submissions are rejected** (they are not waved through). |
| `RECAPTCHA_MIN_SCORE` | No | `0.5` | Minimum acceptable score. Expected action: `submit_job`. |
| `RECAPTCHA_BYPASS_IN_DEVELOPMENT` | No | `false` | Honored only when `ENVIRONMENT` is development/testing. |
| `NEXT_PUBLIC_RECAPTCHA_SITE_KEY` | No | unset | Client site key. Served at **runtime** via `window.__ENV`; build-arg is a fallback only. Widget is skipped when absent. |

---

## Email (Resend SMTP relay)

UAT uses Resend's SMTP relay at `smtp.resend.com:465` with SSL.
Sender is `noreply@xibodev.com` (domain verified in Resend).

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SMTP_HOST` | No | — | SMTP server hostname. If absent, email is silently disabled. UAT: `smtp.resend.com`. |
| `SMTP_PORT` | No | `587` | SMTP port. UAT: `465` (SSL). |
| `SMTP_USERNAME` | No | — | SMTP auth username. Resend uses the literal string `resend`. |
| `SMTP_PASSWORD` | No | — | SMTP auth password. For Resend, this is the API key (`re_...`). |
| `SMTP_USE_SSL` | No | `false` | Use SSL (SMTP_SSL). Set `true` for port 465. |
| `SMTP_USE_TLS` | No | `false` | Use STARTTLS. Set `true` for port 587. Mutually exclusive with SSL. |
| `FROM_EMAIL` | No | — | Sender address (e.g., `Employed <noreply@xibodev.com>`). Required alongside `SMTP_HOST` for email to send. |
| `ADMIN_EMAIL` | No | — | Recipient for admin notifications (deploy env value: `admin@employed.co.mz`). |
| `FRONTEND_BASE_URL` (fallback `APP_BASE_URL`, then request base URL) | **Yes in deployed envs** | unset | Base for transactional-email links: `/verify-email/{token}` and `/reset-password/{token}` must land on the **frontend**. Without it the backend falls back to the request (API) host — the wrong surface. |

---

## Payments

### Stripe

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `STRIPE_SECRET_KEY` | Prod: Yes | unset | Stripe secret key (`sk_test_...` / `sk_live_...`). |
| `STRIPE_WEBHOOK_SECRET` | Prod: Yes | unset | Webhook signing secret for `POST /webhooks/_stripe/webhook`. |
| `STRIPE_PUBLISHABLE_KEY` | No | unset | Publishable key, passed through to the client at runtime. |

### M-Pesa (Vodacom Mozambique) / e-Mola (Movitel Mozambique)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MPESA_SIMULATOR` / `EMOLA_SIMULATOR` | No | `true` | Adapter mode. The live adapter path is not implemented yet. |
| `MPESA_WEBHOOK_SECRET` / `EMOLA_WEBHOOK_SECRET` | Live: Yes | unset | HMAC secret for verifying callbacks. If absent, callbacks are rejected. |

---

## OAuth providers

| Variable | Provider | Status |
|----------|----------|--------|
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google OAuth 2.0 | Configured (only provider wired) |
| `FACEBOOK_CLIENT_ID` / `FACEBOOK_CLIENT_SECRET` | Facebook Login | Placeholder names only — not wired |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | GitHub OAuth | Placeholder names only — not wired |
| `TWITTER_CLIENT_ID` / `TWITTER_CLIENT_SECRET` | Twitter/X OAuth | Placeholder names only — not wired |

---

## Frontend

| Variable | Default | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | API base URL seen by the browser. **Runtime** via `window.__ENV` (build-arg fallback only); SSR rewrites localhost → `http://backend:8000`. |
| `NEXT_PUBLIC_APP_URL` | `http://localhost:3000` | Single source for the deployment domain (Rule 2): market hosts, `robots.txt`, and `sitemap.xml` all derive from it. Never hardcode domains in `src/`. |
| `NEXT_PUBLIC_SIGN_IN_URL` / `NEXT_PUBLIC_SIGN_UP_URL` | `/sign-in`, `/sign-up` | Auth route overrides. |
| `PORT` / `HOSTNAME` | `3000` / `0.0.0.0` | Standalone server binding (image env). |

---

## Observability

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SENTRY_DSN` | No | — | Backend + frontend server/edge DSN. No-op when unset. **No Sentry project is provisioned yet** (operator TODO). |
| `NEXT_PUBLIC_SENTRY_DSN` | No | — | Browser DSN (build-time embedded — not part of `window.__ENV`). |
| `SENTRY_ENVIRONMENT` / `NEXT_PUBLIC_SENTRY_ENVIRONMENT` | No | `uat` (when DSN set) | Sentry environment tag. |
| `SENTRY_TRACES_SAMPLE_RATE` | No | `0.1` | Tracing sample rate. |
