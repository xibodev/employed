---
last_verified: 2026-06-27T00:00:00Z
git_ref: master
verified_by: prod documentation refresh
---

# API Reference

FastAPI backend base URL: `https://api.joinemployed.com`. Interactive docs are available at `/docs` and `/redoc` when enabled by the running environment.

Authenticated endpoints require `Authorization: Bearer <access_token>`. Responses carry `X-Request-ID` and `X-Market` headers. Request bodies are capped at 1 MiB. Rate limits use Redis fixed windows with in-process fallback.

## Health

### `GET /health` and `HEAD /health`

Readiness probe with DB and Redis checks.

```json
{ "status": "ok", "db": "ok", "redis": "ok" }
```

A degraded dependency returns 503 with `status: degraded`.

## Public jobs

### `GET /api/jobs`

Market-scoped active listings. Market resolves from `X-Forwarded-Host` or `Host`.

Common query params: `page`, `page_size`, `query`, `jobtype`, `remote`, `featured`.

### `GET /api/featuredJobs`

Returns the first currently featured listings for the active market.

### `GET /jobs` / `GET /jobs/{id}`

Canonical job listing routes. Anonymous responses omit gated poster contact details.

## Auth

- Email/password registration and login.
- Email verification and password reset links use the frontend base URL.
- Refresh tokens are supported through the configured refresh-token flow.
- Google OAuth callback: `https://api.joinemployed.com/auth/oauth/google/callback`.

## Companies, memberships, and applications

Company, membership, verification, application, webhook-admin, and export routes are available under their configured API prefixes. Authorization uses permission strings resolved by platform and tenant scope.

## Payments and webhooks

- Stripe runs in test mode; production webhook endpoint is registered at `https://api.joinemployed.com/_stripe/webhook`.
- M-Pesa and e-Mola routes exist for simulator mode.
- Webhook handlers validate signatures where secrets are configured and use Redis replay protection.

## Export

The versioned export API exposes standard schemas under `/export/v1`, including JSON Resume candidates and schema.org job payloads.
