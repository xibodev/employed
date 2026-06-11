---
last_verified: 2026-06-11T01:31:02Z
git_ref: fix/quality-run-2026-06-10 @ 5868453 (28 commits ahead of uat @ 00aa899)
verified_by: quality run 2026-06-10_120309 — codebase cartography
---

# Config & Secrets Map — Employed

Env var **names and consumers only — never values.** Secret values resolve
from GitHub Actions secrets or the Box 3 `/opt/employed/.env` (chmod 600);
see `_integrations/CREDENTIALS.md` for the portfolio policy.

Principle (AI-OPS Rule 11, enforced by EMP-012/013/024): mutable values are
runtime config. Backend reads everything through `backend/app/config.py`
(pydantic-settings, `.env` file support, case-insensitive). Frontend
`NEXT_PUBLIC_*` values are served per-request via `window.__ENV`
(`RuntimeEnvScript`) so changes are a restart, not a rebuild.

## Backend — core

| Var | Default | Consumer | Secret? |
|-----|---------|----------|---------|
| `APP_NAME` | `Employed API` | OpenAPI title | no |
| `ENVIRONMENT` | `development` | HSTS, secure cookies, dev secret fallback, reCAPTCHA bypass gating | no |
| `DEBUG` | `false` | dev-mode detection | no |
| `LOG_LEVEL` | `INFO` | `logging_config.py` | no |
| `DATABASE_URL` | local postgres DSN | SQLAlchemy engine | **yes** (embeds password) |
| `ALEMBIC_DATABASE_URL` | falls back to `DATABASE_URL` | migrations | yes |
| `DATABASE_POOL_SIZE/_MAX_OVERFLOW/_POOL_TIMEOUT/_POOL_RECYCLE` | 5/10/30/1800 | engine pool | no |
| `REDIS_URL` | unset (features degrade to in-process) | rate limit, lockout, JTI revocation, replay cache, arq, `/health` | no (yes if password in DSN) |
| `POSTGRES_USER/PASSWORD/DB` | — | compose `postgres` service only | **yes** |

## Backend — auth

| Var | Default | Consumer | Secret? |
|-----|---------|----------|---------|
| `SECRET_KEY` (alias `JWT_SECRET_KEY`) | dev-only fallback in dev/test; **startup fails without it otherwise** (`ensure_jwt_secret_configured`) | JWT signing | **yes** |
| `JWT_ALGORITHM` | `HS256` | `app/auth/jwt.py` | no |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 30 | access-token TTL | no |
| `REFRESH_TOKEN_EXPIRE_DAYS` | 7 | refresh-token TTL | no |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | unset | Google OAuth | **yes** (secret) |
| `FACEBOOK_/GITHUB_/TWITTER_CLIENT_ID/_SECRET` | unset | placeholders in `deploy/.env.example` — providers not wired | yes if ever set |

## Backend — network trust & abuse protection

| Var | Default | Consumer | Secret? |
|-----|---------|----------|---------|
| `TRUSTED_PROXY_IPS` | loopback + RFC1918 CIDRs | `rate_limit._client_ip` — gates X-Forwarded-For trust (EMP-007/020) | no |
| `CORS_ORIGINS` (alias `BACKEND_CORS_ORIGINS`) | `*` in development, **empty otherwise** | CORS middleware; must list exact frontend origins for credentialed cookie auth | no |
| `RECAPTCHA_SECRET_KEY` (fallback name `RECAPTCHA_V3_SECRET_KEY`) | unset | server-side verify, action `submit_job` (EMP-002/003) | **yes** |
| `RECAPTCHA_MIN_SCORE` | 0.5 | score threshold | no |
| `RECAPTCHA_BYPASS_IN_DEVELOPMENT` | false | honored only when `ENVIRONMENT` is development/testing | no |
| `IP_SALT` | unset | salted hashing of reporter IPs and payer MSISDNs | **yes** |

## Backend — email

| Var | Default | Consumer | Secret? |
|-----|---------|----------|---------|
| `SMTP_HOST` / `SMTP_PORT` | unset / 587 | `app/services/email.py` (no-op when unset) | no |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | unset | Resend relay auth (password = Resend API key) | **yes** (password) |
| `SMTP_USE_TLS` / `SMTP_USE_SSL` | false / false | UAT uses SSL :465 | no |
| `FROM_EMAIL` | unset | sender identity | no |
| `ADMIN_EMAIL` | — | deploy env only (notification target) | no |
| `FRONTEND_BASE_URL` → `APP_BASE_URL` → request base URL | — | email link base: `/verify-email/{token}`, `/reset-password/{token}` land on the **frontend** (EMP-004) | no |

## Backend — payments

| Var | Default | Consumer | Secret? |
|-----|---------|----------|---------|
| `STRIPE_SECRET_KEY` | unset | stripe adapter | **yes** |
| `STRIPE_WEBHOOK_SECRET` | unset | webhook signature verify | **yes** |
| `STRIPE_PUBLISHABLE_KEY` | unset | passthrough to client | no |
| `MPESA_SIMULATOR` / `EMOLA_SIMULATOR` | true | adapter mode | no |
| `MPESA_WEBHOOK_SECRET` / `EMOLA_WEBHOOK_SECRET` | unset | HMAC verify of callbacks (EMP-019) | **yes** |

## Backend — observability

| Var | Default | Consumer | Secret? |
|-----|---------|----------|---------|
| `SENTRY_DSN` | unset → no-op | `init_sentry()` | treat as sensitive |
| `SENTRY_ENVIRONMENT` | `uat` (when DSN set) | Sentry env tag | no |
| `SENTRY_TRACES_SAMPLE_RATE` | 0.1 | tracing sample | no |

## Frontend

| Var | Default | Consumer | Runtime or build? |
|-----|---------|----------|-------------------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | `runtime-config.ts#getApiUrl` → `api.ts`; SSR rewrites localhost → `http://backend:8000`; also in CSP `connect-src` | **runtime** via `window.__ENV` (EMP-012); build-arg fallback only |
| `NEXT_PUBLIC_RECAPTCHA_SITE_KEY` | unset | `RecaptchaWidget` | **runtime** via `window.__ENV` |
| `NEXT_PUBLIC_APP_URL` | `http://localhost:3000` | `market.ts` (market hosts), `robots.ts`, `sitemap.ts` — single source for the deployment domain (EMP-013/024, Rule 2) | runtime (server-side reads) |
| `NEXT_PUBLIC_SIGN_IN_URL` / `NEXT_PUBLIC_SIGN_UP_URL` | `/sign-in`, `/sign-up` | `frontend/.env.example` | build |
| `PORT` / `HOSTNAME` | 3000 / 0.0.0.0 | standalone server | image env |

## Where values live per environment

| Environment | Source of values |
|-------------|------------------|
| Local dev/test | `deploy/.env.example` → `.env` (committed example holds names + dev-only placeholders) and `frontend/.env.example` |
| CI | inline non-secret test values in `ci.yml` (test DB/Redis DSNs, test secret key) |
| UAT (Box 3) | `/opt/employed/.env`, upserted by `deploy-uat.yml` from GitHub Actions secrets (`EMPLOYED_UAT_*`, `BOX3_*`) |

## Known gaps (this branch vs deploy pipeline)

`deploy-uat.yml` does not yet upsert: `FRONTEND_BASE_URL`,
`NEXT_PUBLIC_APP_URL`, `CORS_ORIGINS`, `ENVIRONMENT`, `SENTRY_DSN`,
`SENTRY_ENVIRONMENT`, `TRUSTED_PROXY_IPS` (default acceptable for Box 3
Caddy-on-localhost). All are documented as names in `deploy/.env.example`
(EMP-011 commit) and must be added before/with the next UAT deploy — see
DEPLOYMENT_TOPOLOGY.md "Deploy-time env gaps".
