---
last_verified: 2026-06-14T00:00:00Z
git_ref: working-tree (fix/quality-run-2026-06-10 lineage; uat baseline 00aa899)
verified_by: codebase-cartographer — FP-CARTO-007 doc refresh (2026-06-14)
---

# Config & Secrets Map — Employed

Env var **names and consumers only — never values.** Secret values resolve
from GitHub Actions secrets or the Box 3 `/opt/employed/.env` (chmod 600);
see `docs/operations/INFRASTRUCTURE.md` for the portfolio policy.

Principle (runtime config, enforced by EMP-012/013/024): mutable values are
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

> **Planned migration — Resend → AWS SES (config-level, not in code yet).**
> The SMTP vars below currently point at **Resend** (password = Resend API
> key, apex `xibodev.com` sender). The portfolio standard / target is **AWS
> SES (eu-west-1 default)** — the same backend Resend wraps, so the swap is
> the same `SMTP_*` vars repointed at SES SMTP endpoints + a sender-domain
> change, not a code change. **Target `FROM_EMAIL` = `noreply@employed.xibodev.com`**
> once `employed.xibodev.com` is DKIM-verified on SES; **until verified the
> product MUST fall back to `noreply@xibodev.com`** (apex, already on Resend)
> or mail bounces. Employed is on the priority SES bulk-verify list
> (`equilibria`/`kumbuka`/`nagare`/`employed`). **Status: pending SES domain
> verification.** Source: `docs/operations/INFRASTRUCTURE.md` (Email —
> transactional). SES SMTP credential *values* live in GH
> secrets / Box 3 `.env`, never in this repo.

| Var | Default | Consumer | Secret? |
|-----|---------|----------|---------|
| `SMTP_HOST` / `SMTP_PORT` | unset / 587 | `app/services/email.py` (no-op when unset). **CURRENT:** Resend SMTP host. **TARGET:** SES SMTP endpoint (eu-west-1) — planned | no |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | unset | relay auth. **CURRENT:** Resend (password = Resend API key). **TARGET:** SES SMTP user/password — planned | **yes** (password) |
| `SMTP_USE_TLS` / `SMTP_USE_SSL` | false / false | UAT uses SSL :465 | no |
| `FROM_EMAIL` | unset | sender identity. **CURRENT:** `noreply@xibodev.com` (apex, Resend). **TARGET:** `noreply@employed.xibodev.com` once SES-DKIM-verified, else fall back to the apex — planned | no |
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

> **Planned migration — Sentry → Bugsink on Box 0 (DSN-only, not in code yet).**
> The SDK is wired both ends but **no DSN is set** (no-op). The portfolio
> error-tracking standard since 2026-06-11 is **Bugsink self-hosted on Box 0**
> (`https://errors.xibodev.com`, stack `xibodev-atlas/box0/`), which is
> Sentry-SDK compatible. **When `SENTRY_DSN` is finally set its value MUST be a
> Bugsink DSN** — backend project `employed-api`, frontend project
> `employed-web`/`employed-uat`, team `xibodev` — **never a new Sentry SaaS
> project** (legacy org `nmtss` is read-only for old events). **Status:
> pending DSN provisioning.** Source: `docs/operations/INFRASTRUCTURE.md` (Error
> tracking). DSN *value* lives in the `EMPLOYED_UAT_SENTRY_DSN` GH secret /
> Box 3 `.env`, never in this repo.

| Var | Default | Consumer | Secret? |
|-----|---------|----------|---------|
| `SENTRY_DSN` (frontend: `NEXT_PUBLIC_SENTRY_DSN`) | unset → no-op | `init_sentry()` (backend) + `@sentry/nextjs` (frontend). **CURRENT:** unset. **TARGET:** a Bugsink DSN on Box 0 — planned, pending provisioning | treat as sensitive |
| `SENTRY_ENVIRONMENT` | `uat` (when DSN set) | error-tracking env tag (Sentry SDK / Bugsink) | no |
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

**Resolved on branch, pending merge (BL-001 / CARTO-002, 2026-06-11):**
`deploy-uat.yml` now upserts `FRONTEND_BASE_URL`, `NEXT_PUBLIC_APP_URL`,
`CORS_ORIGINS` (exact UAT origins), `ENVIRONMENT=uat`, `SENTRY_DSN` (from the
optional `EMPLOYED_UAT_SENTRY_DSN` Actions secret; empty value = backend
no-op) and `SENTRY_ENVIRONMENT=uat`. Takes effect on the first post-merge
deploy. Remaining deliberate gap: `TRUSTED_PROXY_IPS` is not upserted — the
loopback/RFC1918 default is correct for Box 3 Caddy-on-localhost. See
DEPLOYMENT_TOPOLOGY.md "Deploy-time env gaps".

**Planned migrations (target state, not in code yet):** when
`EMPLOYED_UAT_SENTRY_DSN` is eventually populated, its value must be a
**Bugsink DSN on Box 0** (not a Sentry SaaS DSN). And the `SMTP_*`/`FROM_EMAIL`
values are slated to move from Resend to **AWS SES (eu-west-1)** with sender
`noreply@employed.xibodev.com` (Resend apex fallback until SES-verified). Both
are config-level swaps — see the per-section notes above and
`docs/operations/INFRASTRUCTURE.md`.
