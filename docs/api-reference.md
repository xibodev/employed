---
last_verified: 2026-06-11T02:02:49Z
git_ref: fix/quality-run-2026-06-10 (uat baseline 00aa899)
verified_by: doc-drift audit, quality run 2026-06-10_120309
---

# API Reference

> FastAPI backend. Current UAT base URL: `https://api.employed.xibodev.com`
> (the deployment domain is env-derived — `NEXT_PUBLIC_API_URL` — never
> hardcoded). Interactive docs at `/docs` (Swagger UI) and `/redoc`.
>
> Authenticated endpoints require `Authorization: Bearer <access_token>`.
> Every response carries `X-Request-ID` and `X-Market` headers. Request
> bodies are capped at 1 MiB (413 beyond). Rate limits are per client IP
> (Redis fixed-window; in-process fallback without Redis).
>
> Canonical route table: `docs/architecture/API_MAP.md`.

> **Live-UAT divergence:** this reference describes the code on branch
> `fix/quality-run-2026-06-10` (unmerged). The deployed UAT (`uat` @
> `00aa899`) differs in known-broken ways until the branch ships: email
> verification/reset links point at the API host (405 on click), anonymous
> job posting always fails reCAPTCHA, malformed verify/reset tokens return
> 500 instead of 400, `/admin/reports` 500s when reports exist, the refresh
> token is not set as an httpOnly cookie, and `X-Forwarded-Host` is ignored
> for market resolution. See `docs/product/RELEASE_NOTES.md`.

---

## Health

### `GET /health` (also `HEAD`)

Liveness/readiness probe with DB + Redis component checks (2 s timeout each).
Used by the deploy pipeline smoke test and UptimeRobot. No auth, no rate
limit, excluded from the OpenAPI schema.

**Response `200`:**

```json
{ "status": "ok", "db": "ok", "redis": "ok" }
```

**Response `503`** (degraded — one or more components failing):

```json
{ "status": "degraded", "db": "error", "redis": "ok" }
```

---

## Public API — `/api`

### `GET /api/jobs`

Market-scoped active job listings. Market is resolved from the
`X-Forwarded-Host`/`Host` header subdomain. Rate limit 60 req/min/IP.

**Query parameters:**

| Param | Type | Default | Max | Description |
|-------|------|---------|-----|-------------|
| `page` | int | `1` | — | Page number (1-indexed) |
| `page_size` | int | `20` | `100` | Results per page |
| `query` | string | — | — | Search on title/company |
| `jobtype` | string | — | — | Filter by job type (e.g., `Full Time`) |
| `remote` | bool | — | — | Filter by remote flag |

**Response `200`:** `{ "items": [JobRead...], "total": n, "page": 1, "page_size": 20 }`
(`site_url` on each item derives from the env-configured app URL).

The `contact` field is **excluded** from public responses.

### `GET /api/featuredJobs`

First 3 currently-featured listings for the current market. Rate limit
60 req/min/IP. Contact excluded.

---

## Auth — `/auth`

### `POST /auth/register` — rate limit 5/60 s

**Body:** `{ "email": "...", "password": "..." }`

Always returns the neutral "check your email" response (no account
enumeration). Sends a verification email whose link targets the **frontend**:
`{FRONTEND_BASE_URL}/verify-email/{token}`.

### `POST /auth/login` — rate limit 10/60 s

**Body:** `{ "email": "...", "password": "..." }` → `TokenResponse`.

**Lockout:** 5 failed attempts within 15 minutes → 15-minute lockout, keyed
by (email, client IP) in Redis (in-process fallback without Redis).

Browsers additionally receive the refresh token as an httpOnly cookie
`employed_refresh_token` (path `/auth`, SameSite=Lax, Secure outside dev).

### `POST /auth/refresh`

Refresh token from the body (non-browser clients) **or** the httpOnly cookie.
Checks Redis JTI revocation and `password_changed_at`; rotates the cookie.

### `POST /auth/logout`

Revokes the refresh JTI (body or cookie); always clears the cookie; returns
200 even with a garbage body.

### `POST /auth/verify-email/{token}`

Token in the **path** (not a query param). Malformed/garbage token → `400`.

### `POST /auth/forgot-password` — rate limit 3/60 s

**Body:** `{ "email": "..." }` — neutral response; sends a frontend link
`{FRONTEND_BASE_URL}/reset-password/{token}`.

### `POST /auth/reset-password/{token}` — rate limit 5/60 s

**Body:** `{ "new_password": "..." }` with the token in the path. Malformed
token → `400`. Bumps `password_changed_at` (invalidates older refresh tokens).

### `GET /auth/oauth/{provider}`

307 redirect to the provider consent page. Only `google` is configured.

### `GET /auth/oauth/{provider}/callback`

Exchanges the code and issues tokens. Linking to an existing account by
email requires the provider's verified-email claim; unverified → `403`.

**Redirect URI for Google UAT:**
`https://api.employed.xibodev.com/auth/oauth/google/callback`

---

## Jobs — `/jobs`

Market-scoped via `MarketMiddleware` (`X-Forwarded-Host` → `Host`).

### `GET /jobs`

Public. Active jobs in the market country. Same params as `/api/jobs`;
search/filter/count/order/pagination run in SQL.

### `GET /jobs/featured`

Public. Up to 3 random featured (`featured_through ≥ now`) active market jobs.

### `GET /jobs/count`

Public. Same filters as the list, returns the total only.

### `GET /jobs/mine`

**Auth:** Bearer. Caller's jobs, any status.

### `GET /jobs/{job_id}`

Optional auth. 404 outside the current market (unless admin); non-active
listings are visible only to the owner or an admin.

### `POST /jobs` → `201 JobRead`

Optional auth. **Anonymous:** requires a reCAPTCHA v3 token (action
`submit_job`, score ≥ `RECAPTCHA_MIN_SCORE`). **Authenticated:** requires a
verified email. `country` is force-set from the current market — any
client-supplied value is ignored. Owner receives a submission email.

### `PUT /jobs/{job_id}`

**Auth:** Bearer + verified email; owner or admin. An owner edit of an
`active` job resets it to `pending` (with a status-history entry).

### `DELETE /jobs/{job_id}` → `204`

**Auth:** Bearer; owner or admin.

### `POST /jobs/{job_id}/deactivate?filled=`

**Auth:** Bearer; owner or admin. `active` → `filled`/`inactive`; the owner
is notified by email when an admin deactivates.

---

## Payments — `/payments`

### `GET /payments/providers`

Public. Providers + featured price for the active market (MZ: mpesa, emola,
stripe; MX: stripe).

### `POST /payments/initiate` → `201 PaymentInitiateResponse`

**Auth:** Bearer + verified email; job must belong to the caller and be
`pending` or `active`; provider must be in the market's list. An existing
open intent for the same job is returned instead of creating a duplicate.

**Body:** `{ "job_id": "...", "provider_key": "stripe"|"mpesa"|"emola", "payer_msisdn": "..." (mobile money) }`

Response: `{ intent_id, provider_key, status, kind, redirect_url?, provider_ref? }` —
Stripe returns a `redirect_url` to Checkout; mobile money returns status
`awaiting_user`.

### `GET /payments/{intent_id}/status`

**Auth:** Bearer; intent owner. Polled by the frontend `PaymentPoller`.

### `POST /payments/{intent_id}/cancel`

**Auth:** Bearer; intent owner. Non-terminal intents only.

---

## Reports — `/reports`

### `POST /reports` → `201 ReportRead`

Optional auth. Reasons: `spam`, `scam`, `discriminatory`, `wrong_country`,
`expired_or_filled`, `duplicate`. Anonymous reporters are stored as a salted
IP hash.

### `PATCH /reports/{report_id}/resolve`

**Auth:** admin. Resolutions: `reviewed`, `dismissed`, `job_removed`.

---

## Webhooks — mounted under `/webhooks`

> The router is mounted with the `/webhooks` prefix — the bare
> `/_stripe/webhook` path **404s**. Provider dashboards must use the full
> paths below. Excluded from the OpenAPI schema.

### `POST /webhooks/_stripe/webhook`

`Stripe-Signature` verified against `STRIPE_WEBHOOK_SECRET`; body must be raw
bytes. **Handled events:** `checkout.session.completed`,
`checkout.session.async_payment_succeeded`,
`checkout.session.async_payment_failed`, `charge.refunded`,
`charge.dispute.created`. Idempotent via a replay cache.

### `POST /webhooks/_mpesa/callback`

HMAC-SHA256 via `x-mpesa-signature` or `x-callback-signature` header, secret
`MPESA_WEBHOOK_SECRET`. The payload **must** include a timestamp within
5 minutes (missing/old → `400`); deliveries are replay-deduped.

### `POST /webhooks/_emola/callback`

Same contract as M-Pesa with `x-emola-signature` and `EMOLA_WEBHOOK_SECRET`.

---

## Admin — `/admin` (all require the `admin` role)

### `GET /admin/jobs?status=&page=&page_size=`

All markets, any status; `page_size` ≤ 200.

### `PATCH /admin/jobs/{job_id}/status`

Set status (`pending`/`active`/`flagged`/`inactive`/`filled`); appends to
`status_history`.

### `PATCH /admin/jobs/bulk-status`

Bulk variant of the above.

### `GET /admin/users?q=`

Without `q`: admins only. With `q` (2–120 chars): searches **all** users by
email/name (so non-admins can be found and promoted).

### `POST /admin/users/{user_id}/roles/{role}` / `DELETE .../roles/{role}`

Grant/revoke a role; only `admin` is accepted.

### `GET /admin/reports?resolution=`

Up to 200 reports.

---

## Profiles — `/profiles`

### `GET /profiles/{user_id}`

Public talent profile (keyed by user id, not username). Active profiles only.

### `POST /profiles` → `201` / `PUT /profiles`

**Auth:** Bearer. Upsert / update the caller's own profile.

### `POST /profiles/versions` → `201 ProfileVersionSummary`

**Auth:** Bearer. Saves an immutable JSON Resume snapshot of the caller's live
profile. An optional `json_resume` body updates the live working copy first; the
live profile is materialised on first save. Invalid JSON Resume → `422`.

### `GET /profiles/versions`

**Auth:** Bearer. Lists the caller's profile versions, oldest first.

### `GET /profiles/versions/{version_id}` → `ProfileVersionRead`

**Auth:** Bearer; owner only. A single immutable version; `404` if missing or
not owned.

---

## Companies — `/companies`

> Two-layer RBAC: tenant-scoped endpoints are guarded by `require_permission`
> (platform role or active-membership tenant role). See
> `docs/architecture/RBAC_AND_TENANCY.md`.

### `POST /companies` → `201 CompanyRead`

**Auth:** Bearer. Creates a company; `market` is taken from the request market
context (never the client). The caller becomes the active `org_owner` (atomic).
`409` on conflict.

### `GET /companies/{company_id}` → `CompanyRead`

**Auth:** Bearer. `404` if missing. The signing secrets of any webhook endpoints
are never included.

### `POST /companies/{company_id}/verify-domain` → `CompanyRead`

**Auth:** permission `company:verify_domain`. Body selects DNS TXT
(`expected_token`) or matching-member-email proof. On success the domain is
appended to `verified_email_domains` and the `domain verified` badge attached; a
failed proof → `422` (no change).

---

## Memberships — `/companies/{company_id}/members`

### `GET ` / `POST ` (list / invite)

**Auth:** permission `company:manage_members`. Invite creates an `invited`
membership and records `invited_by`; `201`.

### `POST /{membership_id}/accept`

**Auth:** Bearer — the invited user only. Moves `invited` → `active`. Accepting a
non-`invited` membership → `409` (unchanged); accepting someone else's → `403`.

### `POST /{membership_id}/suspend`

**Auth:** permission `company:manage_members`. Sets status `suspended`, which
revokes that membership's tenant permissions.

---

## Applications

### `GET /companies/{company_id}/applications` → `[ApplicationRead]`

**Auth:** permission `application:review`. Lists a company's applications; without
the permission → `403`.

### `PATCH /applications/{application_id}/status` → `ApplicationRead`

**Auth:** permission `application:advance` (resolved from the application's
company). Advances the pipeline stage (`applied`/`reviewed`/`shortlisted`/
`rejected`/`hired`), persists the new stage, writes an audit row, and emits
`application.status_changed`. Without the permission → `403`.

---

## Moderation & verification — `/moderation`

Platform publication moderation and the shared verification state machine. Each
action writes an audit row; an illegal verification transition → `409`.

### `POST /moderation/jobs/{job_id}/block`

**Auth:** permission `job:block`. Publication status → `flagged` (leaves public
visibility).

### `POST /moderation/jobs/{job_id}/unpublish`

**Auth:** permission `job:unpublish`. Publication status → `inactive`.

### `POST /moderation/jobs/{job_id}/mark-review`

**Auth:** permission `job:mark_review`. `verification_status` → `flagged`.

### `POST /moderation/jobs/{job_id}/verify`

**Auth:** permission `job:verify`. `verification_status` → `verified`.

### `POST /moderation/companies/{company_id}/verify`

**Auth:** permission `company:verify`. Company `verification_status` → `verified`.

### `POST /moderation/profiles/{profile_id}/verify`

**Auth:** permission `profile:verify`. Profile `verification_status` → `verified`.

---

## Webhook endpoints — `/webhook-endpoints`

Outbound webhook endpoint management (distinct from the inbound payment webhooks
under `/webhooks`). The signing `secret` is never returned.

### `POST /webhook-endpoints` → `201 WebhookEndpointRead`

**Auth:** permission `company:manage` (company from the body; a platform-level
endpoint with `company_id` omitted requires the permission across all tenants).
Registers an endpoint and its event subscriptions.

### `GET /webhook-endpoints?company_id=`

**Auth:** permission `company:manage` (scoped to `company_id` when provided, else
platform-level). Lists endpoints.

### `DELETE /webhook-endpoints/{endpoint_id}` → `WebhookEndpointRead`

**Auth:** permission `company:manage` (the endpoint's company). Soft delete
(`active = false`); delivery history is retained.

---

## Export — `/export/v1`

Versioned (path segment), read-only. **Auth:** Bearer (any valid token). A
nonexistent identifier → `404`.

### `GET /export/v1/candidates/{id}`

Candidate as a JSON Resume document (resolves a live `Profile` or a
`ProfileVersion`).

### `GET /export/v1/positions/{id}` (alias `GET /export/v1/jobs/{id}`)

Job as schema.org `JobPosting` JSON-LD. `positions` follows HR Open Standards
(*PositionOpening*); `jobs` is the schema.org-parity alias.

### `GET /export/v1/applications/{id}`

Normalized Application object.

---

## Users — `/users`

### `GET /users/me`

Current user. Returns snake_case fields (e.g. `email_verified`).

### `GET /users/me/export` — rate limit 5/hour

Data export: user + jobs + profile + payment intents + reports.

### `POST /users/me/resend-verification`

Resend the verification email.

### `POST /users/me/request-deletion`

Schedules account deletion at now + 30 days (worker cron hard-deletes).

### `POST /users/me/cancel-deletion`

Cancels a pending deletion request.

---

## Frontend-local endpoint

### `GET /api/health` (frontend origin)

`frontend/src/app/api/health/route.ts` — static
`{ "status": "ok", "service": "employed-frontend" }`; container healthcheck
target.
