---
last_verified: 2026-06-11T01:31:02Z
git_ref: fix/quality-run-2026-06-10 @ 5868453 (28 commits ahead of uat @ 00aa899)
verified_by: quality run 2026-06-10_120309 — codebase cartography
---

# Architecture Overview — Employed

Multilingual job board for Mozambique (MZ) and Mexico (MX). Companies post
jobs, candidates browse localized listings, admins moderate listings before
they go live. Featured-listing payments via Stripe (live-capable) and
M-Pesa/e-Mola (simulator by default).

## System shape

```
 browser (mz.* / mx.* / apex host)
    │
    ▼
 Caddy (Box 3) ──► frontend  Next.js 15 standalone     :3000 (host 3300)
    │                 │  server-side fetch + client fetch, both send
    │                 │  X-Forwarded-Host = market hostname
    ▼                 ▼
 Caddy (api.*) ──► backend   FastAPI / uvicorn          :8000 (host 3301)
                      │
        ┌─────────────┼──────────────┐
        ▼             ▼              ▼
   PostgreSQL 16   Redis 7      arq worker (same image as backend)
   (SQLAlchemy 2)  (queue, rate limit, lockout,   cron: expire jobs,
                    JTI revocation, webhook       delete scheduled accounts,
                    replay dedupe)                settle simulated intents
```

Sources: `deploy/docker-compose.prod.yml`, `backend/app/main.py`,
`backend/app/workers/`, `frontend/src/lib/api.ts`.

## Market & locale resolution (core invariant)

One frontend and one API serve both markets; the **request hostname picks the
market**, and the market picks the default locale:

| Host label | Market | Country scope | Default locale |
|------------|--------|---------------|----------------|
| `mx.*` | MX | Mexico | `es` |
| `mz.*` | MZ | Mozambique | `pt` |
| anything else | MZ (default) | Mozambique | `pt` |

- Backend: `MarketMiddleware` (`backend/app/middleware/market.py`) prefers
  `X-Forwarded-Host` (first value of a comma-chain) over `Host`, because in the
  split-host topology the API's own Host header (`api.*`) never carries a
  market label (EMP-001). Resolved market lands on `request.state.market`; the
  response echoes it in an `X-Market` header. Registry:
  `backend/app/services/market.py`.
- Frontend: `frontend/src/lib/market.ts` mirrors the same resolution
  (`resolveMarketFromHeaders`); the API client
  (`frontend/src/lib/api.ts#apiFetch`) always forwards the browser/server host
  as `X-Forwarded-Host`. Locale: `frontend/src/i18n/request.ts` +
  `frontend/middleware.ts` (`mx.*` → `es`, else `pt`; `en` catalog exists for
  explicit use). Locale codes are **en/pt/es only**.
- All market hostnames derive from the single `NEXT_PUBLIC_APP_URL` env var —
  no domains in source (EMP-013/024). `robots.ts`/`sitemap.ts` derive from the
  same helper.
- Jobs are stamped with the active market's country at creation; listings,
  counts and featured queries are market-scoped (`backend/app/routers/jobs.py`).

## Backend request pipeline

Middleware order (outermost → innermost; `backend/app/main.py#create_app`,
Starlette semantics: last added runs outermost):

1. CORS (`CORS_ORIGINS`; wildcard only in development — credentialed cookie
   auth requires explicit origins)
2. `MarketMiddleware`
3. `SecurityHeadersMiddleware` — nosniff, frame-deny, referrer policy, HSTS
   outside development
4. `RequestBodySizeLimitMiddleware` — 1 MiB cap, 413 beyond
5. `request_context_middleware` — `X-Request-ID` propagation + logging context

Plus global handlers: 422 validation shaping, 500 catch-all (no internals
leaked). `/health` (GET+HEAD) checks DB and Redis with 2 s timeouts and
returns 503 with `{"status": "degraded"}` on component failure.

## Authentication model

Source: `backend/app/routers/auth.py`, `backend/app/auth/`,
`frontend/src/contexts/AuthContext.tsx`.

- **Primary**: email/password accounts. Register → verification email →
  login. JWT bearer **access token** (HS256, default 30 min,
  `ACCESS_TOKEN_EXPIRE_MINUTES`) + **refresh token** (default 7 days,
  `REFRESH_TOKEN_EXPIRE_DAYS`).
- **Refresh transport (EMP-006)**: response body (non-browser clients) AND
  httpOnly cookie `employed_refresh_token` (SameSite=Lax, `path=/auth`,
  Secure outside dev). The frontend keeps the refresh token **in memory only**
  (never localStorage; legacy key is actively scrubbed) and relies on the
  cookie across reloads. The access token is kept in localStorage
  (`employed_token`) and mirrored into a non-httpOnly cookie of the same name
  so `frontend/middleware.ts` can gate routes; `employed_is_admin` cookie is a
  UX hint only — authorization is enforced server-side by `require_admin`.
- **Revocation**: logout revokes the refresh JTI in Redis
  (`app/auth/revocation.py`); password change invalidates older tokens via
  `password_changed_at`.
- **Brute force**: login lockout keyed by (email, client IP) in Redis;
  rate limits on register/login/forgot/reset (see API_MAP.md). Client IP
  honors `X-Forwarded-For` only from trusted proxies
  (`TRUSTED_PROXY_IPS`, default loopback + RFC1918), using the rightmost
  value (EMP-007/020).
- **OAuth**: Google only (`/auth/oauth/google` + callback). Account linking
  by email requires the provider's verified-email claim; unverified-email
  OAuth linking is rejected with 403 (EMP-018). Facebook/GitHub/Twitter env
  slots exist but are not configured and have no UI.
- **Lookups**: auth user lookups are indexed SQL queries (unique
  `users.email`, lowercase-normalized on write; JSONB containment for
  `oauth_providers`) — no full-table Python scans (EMP-005).

## Job lifecycle & moderation

- Statuses: `pending → active → filled | inactive` (+ `flagged`); enum in
  `backend/app/models/enums.py`.
- Anonymous submissions require reCAPTCHA v3 with the enforced action
  `submit_job` and min score `RECAPTCHA_MIN_SCORE` (EMP-002/003);
  authenticated submitters must be email-verified.
- Non-active listings (including contact details) are visible only to the
  owner or admins; owner edits of an active listing reset it to `pending`
  for re-moderation (EMP-008).
- 90-day expiry by the worker cron (`expire_old_jobs`, every 6 h): status →
  `inactive` with reason `expired` recorded in `status_history` and
  `expired_at` set (EMP-017).
- Public list/search/count push search (pg_trgm ILIKE), filters, ORDER BY,
  COUNT and pagination into SQL (EMP-010).
- Transactional email on submission, status change, and admin deactivation
  (owner notified, not the acting admin — EMP-016). Email links point at
  **frontend** pages built from `FRONTEND_BASE_URL`/`APP_BASE_URL`
  (EMP-004).

## Payments

Source: `backend/app/routers/payments.py`, `backend/app/payments/`,
`backend/app/webhooks/`.

- Feature-a-job purchase: `POST /payments/initiate` creates a
  `PaymentIntent` for the job in the active market (MX: Stripe only;
  MZ: M-Pesa, e-Mola, Stripe; amounts per-market in the market registry).
- Stripe adapter is live-capable (test keys in UAT); webhook mounted at
  `POST /webhooks/_stripe/webhook` with signature verification
  (`STRIPE_WEBHOOK_SECRET`).
- M-Pesa/e-Mola run in **simulator mode by default** (`MPESA_SIMULATOR` /
  `EMOLA_SIMULATOR` default true); the arq task `settle_simulated_intent`
  settles them. Their callbacks (`/webhooks/_mpesa/callback`,
  `/webhooks/_emola/callback`) require an HMAC-SHA256 signature
  (`MPESA_WEBHOOK_SECRET`/`EMOLA_WEBHOOK_SECRET`) and a **mandatory payload
  timestamp** within a 5-minute window, with Redis-backed replay dedupe
  (EMP-019).
- Settlement extends `jobs.featured_through` and appends to
  `featured_charge_history` (`app/payments/settlement.py`).
- MSISDNs are stored truncated (4 chars) + salted hash (`IP_SALT`).

## Frontend architecture

- Next.js 15 App Router, React 19, server components by default; standalone
  output. SSR fetches rewrite `localhost` API URLs to the compose-internal
  `http://backend:8000` (`src/lib/api.ts`).
- **Runtime config (EMP-012, Rule 11)**: `NEXT_PUBLIC_API_URL` and
  `NEXT_PUBLIC_RECAPTCHA_SITE_KEY` resolve at request time via a per-request
  `window.__ENV` script (`RuntimeEnvScript`) with build-time inlining only as
  fallback — changing them is a container restart, not a rebuild.
- Route protection in `frontend/middleware.ts` (cookie presence only);
  real authorization is the API's.
- Admin dashboard degrades per-panel (`Promise.allSettled` + error banners)
  instead of blanking when one endpoint fails (EMP-026b).
- i18n: next-intl, hostname-driven; pt/es catalogs complete across auth,
  job-detail, account, my-jobs and post-job surfaces (EMP-027).
- CSP + security headers in `next.config.ts`.

## Background processing

`arq` worker (same image as the API, command
`arq app.workers.config.WorkerSettings`):

| Job | Schedule | Effect |
|-----|----------|--------|
| `expire_old_jobs` | cron hours 0/6/12/18 | active jobs >90 days → inactive (+history/`expired_at`) |
| `delete_scheduled_accounts` | cron hour 3 | hard-delete accounts past their 30-day deletion window |
| `settle_simulated_intent` | enqueued | settles simulator-mode mobile-money intents |

Worker is importable without `REDIS_URL` (falls back to a local DSN default,
EMP-017 follow-up); prod compose gives it a Redis-ping healthcheck instead of
the inherited HTTP one.

## Observability

- Sentry: backend `init_sentry()` (FastAPI+SQLAlchemy integrations) and
  frontend `@sentry/nextjs` configs — both no-op until `SENTRY_DSN` is set
  (projects not provisioned yet; operator action from the 2026-06-10 run).
- Health: API `/health` (GET+HEAD, DB+Redis), frontend `/api/health`
  (static ok). UptimeRobot monitors both (see `docs/operations/uptime-robot.md`).
- Structured logs with request IDs (`backend/app/logging_config.py`).

## Trust boundaries

1. Internet → Caddy (TLS) → frontend/backend containers (loopback-published
   host ports 3300/3301).
2. Browser → API: bearer token; refresh cookie confined to `/auth` path.
3. API → DB/Redis: compose-internal network only; no host exposure in prod
   compose.
4. Webhooks: signature verification + timestamp freshness + replay dedupe
   before any state change.
5. `X-Forwarded-For` trusted only from `TRUSTED_PROXY_IPS`;
   `X-Forwarded-Host` is intentionally client-influenced for market selection
   only — it never drives auth, URLs in emails, or redirects.
