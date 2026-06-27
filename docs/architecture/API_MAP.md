---
last_verified: 2026-06-27T00:00:00Z
git_ref: master
verified_by: codebase-cartographer — FP-CARTO-007 doc refresh (2026-06-14)
---

# API Map — Employed backend

All routes observed in `backend/app/routers/` and `backend/app/webhooks/`,
wired in `backend/app/main.py#create_app`. Auth column: `public` (no auth),
`optional` (works anonymously, richer when authenticated), `user` (valid
access token), `user+verified` (token + verified email), `admin`
(`require_admin`), and `perm:<name>` (two-layer RBAC `require_permission`
guard — platform role or active-membership tenant role; see
RBAC_AND_TENANCY.md). Rate limits are per client IP (Redis fixed-window;
in-process fallback without Redis).

Every response carries `X-Request-ID` and `X-Market` headers. Request bodies
are capped at 1 MiB (413 beyond).

## Health

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| GET, HEAD | `/health` | public | DB + Redis component checks (2 s timeout each); 503 `{"status":"degraded"}` on failure. Excluded from OpenAPI. |

## Auth — `/auth` (`app/routers/auth.py`)

| Method | Path | Auth | Rate limit | Notes |
|--------|------|------|-----------|-------|
| POST | `/auth/register` | public | 5/60 s | Always returns the neutral "check your email" response (no account enumeration); sends verification email with **frontend** link `/verify-email/{token}` (EMP-004) |
| POST | `/auth/login` | public | 10/60 s | Redis lockout keyed (email, client IP); sets httpOnly refresh cookie `employed_refresh_token` (SameSite=Lax, path=`/auth`, Secure outside dev) |
| POST | `/auth/refresh` | refresh token | — | Token from body (non-browser) or httpOnly cookie (EMP-006); checks Redis JTI revocation + `password_changed_at`; rotates cookie |
| POST | `/auth/logout` | optional | — | Revokes refresh JTI in Redis (body or cookie); always clears cookie; 200 even with garbage body |
| POST | `/auth/verify-email/{token}` | public (token) | — | Malformed/garbage token → 400 (EMP-025) |
| POST | `/auth/forgot-password` | public | 3/60 s | Neutral response; sends frontend link `/reset-password/{token}` |
| POST | `/auth/reset-password/{token}` | public (token) | 5/60 s | Malformed token → 400 (EMP-025); bumps `password_changed_at` |
| GET | `/auth/oauth/{provider}` | public | — | Redirect to provider consent (google only configured) |
| GET | `/auth/oauth/{provider}/callback` | public | — | Linking by email requires provider verified-email claim; unverified → 403 (EMP-018) |

## Jobs — `/jobs` (`app/routers/jobs.py`)

Market-scoped via `MarketMiddleware` (X-Forwarded-Host → Host).

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| GET | `/jobs` | public | Active jobs in market country. `page`, `page_size` (≤100), `query` (trgm search on title/company), `jobtype`, `remote`. Search/filters/COUNT/ORDER/pagination in SQL (EMP-010) |
| GET | `/jobs/featured` | public | Up to 3 random featured (featured_through ≥ now) active market jobs |
| GET | `/jobs/count` | public | Same filters as list, total only |
| GET | `/jobs/mine` | user | Caller's jobs, any status |
| GET | `/jobs/{job_id}` | optional | 404 outside market (unless admin); non-active listings only for owner/admin (EMP-008) |
| POST | `/jobs` | optional | Anonymous: reCAPTCHA v3 token required, action `submit_job`, score ≥ `RECAPTCHA_MIN_SCORE` (EMP-002/003). Authenticated: email verification required. Country stamped from market; submission email to owner |
| PUT | `/jobs/{job_id}` | user+verified (owner/admin) | Owner edit of an `active` job resets status to `pending` with history entry (EMP-008) |
| DELETE | `/jobs/{job_id}` | user (owner/admin) | 204 |
| POST | `/jobs/{job_id}/deactivate?filled=` | user (owner/admin) | active → filled/inactive; owner notified when an admin deactivates (EMP-016) |

## Profiles — `/profiles` (`app/routers/profiles.py`)

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| GET | `/profiles/{user_id}` | public | Active profiles only |
| POST | `/profiles` | user | Upsert of the caller's profile, 201 |
| PUT | `/profiles` | user | Update caller's profile |
| POST | `/profiles/versions` | user | Save an immutable JSON Resume snapshot of the caller's live profile (R13.2); optional `json_resume` body updates the live copy first; 201. Invalid JSON Resume → 422 |
| GET | `/profiles/versions` | user | List the caller's profile versions, oldest first |
| GET | `/profiles/versions/{version_id}` | user (owner) | A single immutable version; 404 if not owned/missing |

> Profile-version routes are declared before `/{user_id}` so `versions` is not
> captured as a user id.

## Companies — `/companies` (`app/routers/companies.py`)

Permission checks use the two-layer RBAC model (see RBAC_AND_TENANCY.md);
`perm:<name>` below denotes a `require_permission` guard.

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| POST | `/companies` | user | Create a company; market taken from request context (never the client); caller becomes active `org_owner`. 201; 409 on conflict |
| GET | `/companies/{company_id}` | user | Read a company; 404 if missing |
| POST | `/companies/{company_id}/verify-domain` | perm:`company:verify_domain` | DNS TXT (`expected_token`) or matching-member-email proof; on success appends to `verified_email_domains` + attaches `domain verified` badge; failed proof → 422 |

## Memberships — `/companies/{company_id}/members` (`app/routers/memberships.py`)

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| GET | `` | perm:`company:manage_members` | List a company's memberships |
| POST | `` | perm:`company:manage_members` | Invite a user → `invited` membership, records `invited_by`; 201 |
| POST | `/{membership_id}/accept` | user (the invited user only) | `invited` → `active`; non-invited/foreign → 409/403; status unchanged on failure |
| POST | `/{membership_id}/suspend` | perm:`company:manage_members` | Set status `suspended` (revokes that membership's tenant permissions) |

## Applications — (`app/routers/applications.py`)

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| GET | `/companies/{company_id}/applications` | perm:`application:review` | List a company's applications; lacking the permission → 403 |
| PATCH | `/applications/{application_id}/status` | perm:`application:advance` (resolved from the application's company) | Advance pipeline stage; persists new stage, writes an audit row, emits `application.status_changed`; lacking the permission → 403 |

## Moderation & verification — `/moderation` (`app/routers/verification.py`)

Platform publication moderation and the shared verification state machine. Each
action writes an audit row; illegal verification transitions → 409.

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| POST | `/moderation/jobs/{job_id}/block` | perm:`job:block` | Publication status → `flagged` (leaves public visibility) |
| POST | `/moderation/jobs/{job_id}/unpublish` | perm:`job:unpublish` | Publication status → `inactive` |
| POST | `/moderation/jobs/{job_id}/mark-review` | perm:`job:mark_review` | `verification_status` → `flagged` |
| POST | `/moderation/jobs/{job_id}/verify` | perm:`job:verify` | `verification_status` → `verified` |
| POST | `/moderation/companies/{company_id}/verify` | perm:`company:verify` | Company `verification_status` → `verified` |
| POST | `/moderation/profiles/{profile_id}/verify` | perm:`profile:verify` | Profile `verification_status` → `verified` |

## Export — `/export/v1` (`app/routers/export_api.py`)

Versioned (path segment), read-only; requires a valid bearer token. 404 for a
nonexistent identifier.

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| GET | `/export/v1/candidates/{id}` | user | Candidate as JSON Resume (resolves a `Profile` or `ProfileVersion`) |
| GET | `/export/v1/positions/{id}` | user | Job as schema.org `JobPosting` JSON-LD (HR Open *PositionOpening*) |
| GET | `/export/v1/jobs/{id}` | user | Alias of `/positions/{id}` (hidden from schema) |
| GET | `/export/v1/applications/{id}` | user | Normalized Application object |

## Webhook endpoints — `/webhook-endpoints` (`app/routers/webhooks_admin.py`)

Outbound webhook endpoint management (distinct from inbound payment webhooks
under `/webhooks`). The signing `secret` is never returned in responses.

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| POST | `/webhook-endpoints` | perm:`company:manage` (company from body; platform-level when `company_id` omitted) | Register an endpoint + event subscriptions; 201 |
| GET | `/webhook-endpoints?company_id=` | perm:`company:manage` (scoped/unscoped) | List endpoints; filtered when `company_id` given |
| DELETE | `/webhook-endpoints/{endpoint_id}` | perm:`company:manage` (endpoint's company) | Soft delete (`active = false`); keeps delivery history |

## Payments — `/payments` (`app/routers/payments.py`)

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| POST | `/payments/initiate` | user+verified | Job must belong to caller; provider must be in the market's provider list (MX: stripe; MZ: mpesa/emola/stripe); creates `PaymentIntent`, 201 |
| GET | `/payments/{intent_id}/status` | user (owner) | Polling endpoint used by the frontend `PaymentPoller` |
| POST | `/payments/{intent_id}/cancel` | user (owner) | Non-terminal intents only |
| GET | `/payments/providers` | public | Providers + featured price for the active market |

## Reports — `/reports` (`app/routers/reports.py`)

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| POST | `/reports` | optional | Reasons: spam, scam, discriminatory, wrong_country, expired_or_filled, duplicate; anonymous reporter stored as IP hash |
| PATCH | `/reports/{report_id}/resolve` | admin | Resolutions: reviewed, dismissed, job_removed |

## Admin — `/admin` (`app/routers/admin.py`), all `require_admin`

| Method | Path | Notes |
|--------|------|-------|
| GET | `/admin/jobs?status=&page=&page_size=` | All markets, any status; page_size ≤ 200 |
| PATCH | `/admin/jobs/{job_id}/status` | Set status (pending/active/flagged/inactive/filled); appends `status_history` |
| PATCH | `/admin/jobs/bulk-status` | Bulk variant |
| GET | `/admin/users?q=` | No `q`: admins only. With `q` (2–120 chars): searches all users by email/name so non-admins can be found and promoted (EMP-015) |
| POST | `/admin/users/{user_id}/roles/{role}` | Grant role; only `admin` accepted |
| DELETE | `/admin/users/{user_id}/roles/{role}` | Revoke role; only `admin` accepted |
| GET | `/admin/reports?resolution=` | ≤200 reports; UUID fields serialized as strings (EMP-026a fixed the 500) |

## Users — `/users` (`app/routers/users.py`)

| Method | Path | Auth | Rate limit | Notes |
|--------|------|------|-----------|-------|
| GET | `/users/me` | user | — | Returns snake_case `email_verified` (frontend reads it since EMP-029) |
| GET | `/users/me/export` | user | 5/3600 s | Data export (user + jobs + profile + intents + reports) |
| POST | `/users/me/resend-verification` | user | — | **Observed defect (CARTO-EMP-003):** builds the verify link against the API `request.base_url` (POST-only `/auth/verify-email/{token}`) instead of `FRONTEND_BASE_URL` + the frontend `/verify-email/{token}` page — so a resent link 405s on click, the way the register link did pre-EMP-004. Backend fix tracked as FP-CARTO-003 (out of cartographer scope) |
| POST | `/users/me/request-deletion` | user | — | Schedules deletion at now+30 d; worker cron hard-deletes |
| POST | `/users/me/cancel-deletion` | user | — | |

## Public API — `/api` (`app/routers/public_api.py`, Restivus replacement)

| Method | Path | Auth | Rate limit | Notes |
|--------|------|------|-----------|-------|
| GET | `/api/jobs` | public | 60/60 s | Same filter params as `/jobs`; **contact field excluded**. This is the endpoint the frontend jobs grid calls (`frontend/src/lib/api.ts#getJobs`) |
| GET | `/api/featuredJobs` | public | 60/60 s | First 3 featured, contact excluded |

> Observation: `/api/jobs` and `/api/featuredJobs` still filter in Python over
> `query_all` — the EMP-010 SQL pushdown landed on `/jobs`/`/jobs/count`
> only. Functionally equivalent, but the perf fix does not yet cover the
> public alias the frontend uses.

## Webhooks — mounted under `/webhooks` (`app/webhooks/`)

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| POST | `/webhooks/_stripe/webhook` | Stripe signature (`STRIPE_WEBHOOK_SECRET`) | Mounted prefix means the bare `/_stripe/webhook` path 404s — Stripe dashboard URL must include `/webhooks` (EMP-014) |
| POST | `/webhooks/_mpesa/callback` | HMAC-SHA256 (`MPESA_WEBHOOK_SECRET`, header `x-mpesa-signature`/`x-callback-signature`) | Mandatory payload timestamp within 5 min; Redis replay dedupe (EMP-019) |
| POST | `/webhooks/_emola/callback` | HMAC-SHA256 (`EMOLA_WEBHOOK_SECRET`) | Same timestamp + replay rules |

All webhook routes are excluded from the OpenAPI schema.

## Frontend-local API

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/health` (frontend origin) | `frontend/src/app/api/health/route.ts` — static `{status:"ok"}`; container healthcheck target |
