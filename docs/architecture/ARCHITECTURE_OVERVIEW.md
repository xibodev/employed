---
last_verified: 2026-06-19T00:00:00Z
git_ref: uat (multi-tenant-hiring-platform complete)
verified_by: full implementation doc refresh
---

# Architecture Overview — Employed

Trust-centric, integration-ready hiring platform for Mozambique (MZ) and Mexico (MX). More than a job board, less than a heavy ATS: companies create organizations and post jobs, candidates browse localized listings and apply through a lightweight pipeline, recruiters manage applications through configurable stages, and admins moderate content with verification workflows. Multi-tenant with two-layer RBAC, per-entity verification state machine, composable trust badges, JSON Resume profiles, outbound webhooks, and standard-schema export API. Featured-listing payments via Stripe (live-capable) and M-Pesa/e-Mola (simulator by default).

> **Multi-tenant hiring platform implementation complete.** The platform now includes
> all hiring platform features: `Company` entities with `Membership` management,
> two-layer RBAC (platform + tenant permissions), verification state machine with
> trust badges, version-controlled JSON Resume profiles, `Application` pipeline with
> recruiter workflow, append-only audit trail, webhook system for domain events,
> and versioned export API with standard schemas. Market (geography) and tenant
> (organization) remain orthogonal axes. Legacy job board features are preserved
> unchanged. Details in `RBAC_AND_TENANCY.md`, `VERIFICATION_AND_TRUST.md`,
> `INTEGRATION_AND_EXPORT.md`, `MIGRATION_STRATEGY.md`, and the comprehensive
> `DATA_MODEL.md`/`API_MAP.md`.

## System shape

```
 browser (mz.* / mx.* / apex host)
    │
    ▼
 Caddy (Box 3) ──► frontend  Next.js 15 standalone     :3000 (host 3300)
    │                 │  • tenant context management (companies/memberships)
    │                 │  • company dashboard & member management UI
    │                 │  • applications kanban & list views
    │                 │  • verification status displays
    │                 │  server-side fetch + client fetch, both send
    │                 │  X-Forwarded-Host = market hostname
    ▼                 ▼
 Caddy (api.*) ──► backend   FastAPI / uvicorn          :8000 (host 3301)
                      │  • two-layer RBAC authorization
                      │  • verification state machine
                      │  • trust badge computation
                      │  • JSON Resume profile versioning
                      │  • webhook emission & delivery
                      │  • export API (JSON Resume, JobPosting JSON-LD)
        ┌─────────────┼──────────────┐
        ▼             ▼              ▼
   PostgreSQL 16   Redis 7      arq worker (same image as backend)
   (SQLAlchemy 2)  (queue, rate limit, lockout,   cron: expire jobs,
   + new tables:    JTI revocation, webhook       delete scheduled accounts,
   companies,       replay dedupe, worker         settle simulated intents,
   memberships,     task queue)                   PDF resume rendering,
   applications,                                  webhook delivery + retry
   audit_logs,
   profile_versions,
   webhook_*
```

Sources: `deploy/docker-compose.prod.yml`, `backend/app/main.py`,
`backend/app/workers/`, `frontend/src/lib/api.ts`, migration files
`003_rbac_and_tenancy.py`, `004_migrate_admins.py`, `005_migrate_legacy_profiles_and_jobs.py`.

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

## Authorization model (two-layer RBAC)

Source: `backend/app/services/rbac.py`, `backend/app/models/enums.py`,
`backend/app/services/companies.py`, `backend/app/services/memberships.py`.

The platform implements a **two-layer Role-Based Access Control (RBAC)** system with atomic permissions as the authorization primitive:

### Platform Layer (cross-tenant)
- **platform_super_admin**: Full platform access across all tenants
- **platform_moderator**: Content moderation and verification permissions  
- **platform_support**: Read-only support access

### Tenant Layer (company-scoped)
- **org_owner**: Full company management (created automatically with company)
- **org_admin**: Company administration excluding ownership transfer
- **recruiter**: Job posting and application management
- **member**: View-only access to company resources

### Permission Resolution
1. **Tenant scope resolution**: Determined from target resource's `company_id`
2. **Effective permissions**: `platform_permissions ∪ active_tenant_permissions`
3. **Authorization check**: Action allowed if required permission ∈ effective permissions
4. **Suspended memberships**: Grant zero tenant permissions regardless of role
5. **Independence**: Either platform OR tenant permissions can authorize an action

### Key Permissions
- `job:post`, `job:moderate`, `job:verify` — Job management
- `company:verify`, `company:manage_members` — Company operations  
- `profile:verify`, `user:suspend` — User management
- `platform_user:create`, `platform_role:assign` — Platform administration

The `require_permission(permission_name)` FastAPI dependency handles all authorization checks, resolving tenant scope from path/body parameters and raising 403 on insufficient permissions.

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

## Company & membership management

Source: `backend/app/services/companies.py`, `backend/app/services/memberships.py`,
`frontend/src/components/company/`, `frontend/src/contexts/TenantContext.tsx`.

### Company Creation & Management
- **Company entity**: name, slug (unique per market), description, logo, website, verification status
- **Automatic owner membership**: Creating a company grants `org_owner` + `active` membership
- **Domain verification**: DNS TXT records or matching member emails → `domain verified` trust badge
- **Market scoping**: Each company belongs to one market (MX or MZ)
- **External references**: JSONB field for mapping to external system IDs

### Membership Lifecycle
- **Invitation flow**: `company:manage_members` → create `invited` membership → accept → `active`
- **Role assignment**: `org_owner`, `org_admin`, `recruiter`, `member` with different permission sets
- **Status management**: `invited` → `active` → `suspended` (suspended = zero tenant permissions)
- **Domain auto-membership**: Users with verified emails matching company domains get auto-invited
- **Multi-company support**: Users can hold memberships in multiple companies

### Frontend Integration
- **Tenant context**: Separate from market context, manages active company selection
- **Company switcher**: UI for users with multiple company memberships
- **Company dashboard**: Verification status, member management, domain verification workflow
- **Member management**: Invite, accept, suspend interfaces with permission guards

## Verification & trust system

Source: `backend/app/services/verification.py`, `backend/app/services/trust.py`,
`backend/app/routers/verification.py`.

### Verification State Machine
Single reusable state machine for Company, User identity, Profile, and Job entities:
- **States**: `unverified` → `pending` → `verified`/`rejected`/`revoked`/`flagged`
- **Transitions**: Governed by permission checks (`company:verify`, `job:verify`, etc.)
- **Audit trail**: Every transition writes an append-only audit log entry
- **Atomic operations**: State change + badge reconciliation + audit logging in single transaction

### Trust Badges (Composable)
- **Company badges**: `email verified`, `domain verified`, `business-document verified`, `payment verified`, `activity`
- **Job badges**: `posted by verified company`, `salary disclosed`, `responsive`  
- **Profile badges**: `email verified`, `identity verified`, `phone verified`
- **Derivation**: Pure function computes badges from current entity conditions
- **Reconciliation**: Attach badges when conditions hold, remove when conditions cease

### Domain Verification Flow
1. **DNS TXT method**: Place verification token in `_employed-verify.domain.com` TXT record
2. **Email match method**: Active company members with verified `@domain.com` emails
3. **Success**: `domain verified` badge + add to company's `verified_email_domains` list
4. **Retry logic**: Badge attachment failure retries domain list update

## Application pipeline & profile versioning

Source: `backend/app/services/applications.py`, `backend/app/services/profiles_versioning.py`,
`backend/app/services/application_email.py`, `frontend/src/components/applications/`.

### Profile Versioning (JSON Resume)
- **Live profile**: Single working-copy Profile per user using JSON Resume schema
- **Immutable snapshots**: `save_version()` creates append-only ProfileVersion records
- **Version integrity**: ProfileVersions cannot be modified after creation (DB + service guards)
- **Application linking**: Applications reference specific ProfileVersion for resume data
- **Export compatibility**: JSON Resume format ensures ATS import compatibility

### Application Entity & Pipeline
- **Tracked applications**: First-class Application records with `applied` → `reviewed` → `shortlisted` → `rejected` → `hired` stages
- **Candidate references**: Either `candidate_user_id` (registered users) or `candidate_snapshot` (JSON Resume blob)
- **Dual channels**: Tracked pipeline (default) + email-apply (always available, no silent fallback)
- **Email templates**: Token substitution for `job_title`, `company`, `candidate_name`
- **Webhook emission**: `application.created` and `application.status_changed` events

### Recruiter Workflow
- **Permission gating**: Application access requires active membership with appropriate permissions
- **Multiple views**: List view (table) and kanban board (drag-drop status changes)
- **Status advancement**: Controlled progression through pipeline stages with audit trail
- **Company scoping**: Recruiters see only applications for their company's jobs
- **Audit logging**: Every status change creates audit trail entry + webhook emission

## Job lifecycle & moderation (enhanced)

- Statuses: `pending → active → filled | inactive` (+ `flagged`); enum in
  `backend/app/models/enums.py`.
- **Company posting**: Jobs can be posted on behalf of companies (requires `job:post` permission), setting `company_id`; legacy anonymous jobs have `null company_id`
- **Trust integration**: Jobs posted by verified companies receive `posted by verified company` trust badge
- Anonymous submissions require reCAPTCHA v3 with the enforced action
  `submit_job` and min score `RECAPTCHA_MIN_SCORE` (EMP-002/003);
  authenticated submitters must be email-verified.
- Non-active listings (including contact details) are visible only to the
  owner or admins; owner edits of an active listing reset it to `pending`
  for re-moderation (EMP-008).
- **Verification workflow**: Jobs have `verification_status` field managed by verification state machine
- 90-day expiry by the worker cron (`expire_old_jobs`, every 6 h): status →
  `inactive` with reason `expired` recorded in `status_history` and
  `expired_at` set (EMP-017).
- Public list/search/count push search (pg_trgm ILIKE), filters, ORDER BY,
  COUNT and pagination into SQL (EMP-010).
- Transactional email on submission, status change, and admin deactivation
  (owner notified, not the acting admin — EMP-016). Email links point at
  **frontend** pages built from `FRONTEND_BASE_URL`/`APP_BASE_URL`
  (EMP-004). Current relay is **Resend SMTP** via the `xibodev.com` apex
  sender; the portfolio standard (and planned target) is **AWS SES** — see
  the External services narrative below.

## Webhook system & integration API

Source: `backend/app/services/webhooks.py`, `backend/app/routers/webhooks_admin.py`,
`backend/app/routers/export_api.py`, `backend/app/workers/tasks.py`.

### Outbound Webhooks
- **Event types**: `job.published`, `application.created`, `application.status_changed`
- **Registration**: Companies register webhook endpoints with event subscriptions
- **Fan-out**: Events deliver to ALL subscribed endpoints, none to unsubscribed endpoints  
- **Reliability**: Delivery via arq worker with exponential backoff retry policy
- **Security**: HMAC signature verification + timestamp validation + replay protection
- **Isolation**: Webhook delivery failures never roll back the triggering database transaction

### Webhook Delivery Worker
- **Retry policy**: Exponential backoff `min(2^attempt * 30s, 6h)` with attempt cap
- **Failure tracking**: Attempts count, next_attempt_at scheduling, terminal `failed` state
- **Error capture**: Last error message stored for debugging failed deliveries

### Export API (Versioned, Read-Only)
- **URL versioning**: `/api/export/v1/candidates/{id}` format allows API evolution
- **JSON Resume export**: Candidate profiles returned in standard JSON Resume format
- **JobPosting JSON-LD**: Jobs mapped to schema.org JobPosting structured data
- **Stable identifiers**: UUID `id` fields serve as public, stable entity identifiers
- **404 handling**: Nonexistent entities return proper 404 responses
- **HR Open Standards alignment**: Vocabulary aligned with industry standards where feasible

### External References (Migration-Free Integration)
- **JSONB storage**: `external_refs` field on Company, Job, Profile, User, Application entities
- **No-migration mapping**: Store external system IDs without schema changes
- **Round-trip guarantee**: Data written to `external_refs` loads identically
- **Integration pattern**: Enables bidirectional sync with external ATS systems

## Audit trail & compliance

Source: `backend/app/services/audit.py`, `backend/app/models/audit_log.py`.

### Comprehensive Audit Logging
- **Scope**: All privileged, verification, moderation, and membership actions
- **Data capture**: Actor (user or system), action type, target entity, before/after state, timestamp
- **Append-only design**: AuditLog records can never be updated or deleted
- **System actors**: Support for both user actors (`actor_id`) and system processes (`actor_label`)
- **Immutability guards**: Database-level `before_update` triggers prevent tampering

### Legacy Migration
- **Status history conversion**: Existing `Job.status_history` JSONB migrated to structured audit entries
- **Preservation**: All historical data preserved during migration with full reversibility
- **Audit trail continuity**: Seamless transition from legacy status tracking to comprehensive audit logging

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
- **Runtime config (EMP-012)**: `NEXT_PUBLIC_API_URL` and
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

## Background processing (enhanced)

`arq` worker (same image as the API, command
`arq app.workers.config.WorkerSettings`):

| Job | Schedule | Effect |
|-----|----------|--------|
| `expire_old_jobs` | cron hours 0/6/12/18 | active jobs >90 days → inactive (+history/`expired_at`) |
| `delete_scheduled_accounts` | cron hour 3 | hard-delete accounts past their 30-day deletion window |
| `settle_simulated_intent` | enqueued | settles simulator-mode mobile-money intents |
| `render_resume_pdf` | enqueued | server-side PDF rendering from ProfileVersion + template |
| `deliver_webhook` | enqueued | webhook delivery with exponential backoff retry |

**New hiring platform tasks**:
- **PDF resume rendering**: Generates downloadable resumes from JSON Resume ProfileVersions using predefined templates
- **Webhook delivery**: Reliable outbound HTTP notifications with retry logic for integration events
- **Enhanced audit trail**: All worker actions write audit log entries for compliance tracking

Worker is importable without `REDIS_URL` (falls back to a local DSN default,
EMP-017 follow-up); prod compose gives it a Redis-ping healthcheck instead of
the inherited HTTP one.

## Observability

- Error tracking (CURRENT): the **Sentry SDK is wired both ends** — backend
  `init_sentry()` (FastAPI+SQLAlchemy integrations) and frontend
  `@sentry/nextjs` configs — but both are **no-op until `SENTRY_DSN` is set**.
  No DSN is set today, so error capture is effectively dormant.
- Error tracking (PLANNED — pending DSN provisioning): the portfolio
  error-tracking standard since 2026-06-11 is **Bugsink self-hosted on Box 0**
  (`https://errors.xibodev.com`, stack at `xibodev-atlas/box0/`), which is
  Sentry-SDK compatible. When a DSN is finally provisioned it MUST be a
  **Bugsink** DSN — project `employed-api` (backend) and
  `employed-web` / `employed-uat` (frontend), team `xibodev` — never a new
  Sentry SaaS project. The legacy Sentry SaaS org `nmtss` is kept read-only
  for old events only. Source: `docs/operations/INFRASTRUCTURE.md` (Error
  tracking). Status: SDK code unchanged, DSN swap only.
- Health: API `/health` (GET+HEAD, DB+Redis), frontend `/api/health`
  (static ok). UptimeRobot monitors both today (external; the portfolio
  standard is moving to Gatus on Box 0 per `docs/operations/INFRASTRUCTURE.md`,
  not yet wired here — see `docs/operations/uptime-monitoring.md`).
- Structured logs with request IDs (`backend/app/logging_config.py`).

## External services (current vs planned)

Two portfolio-standard migrations are **planned/target state**, not yet
reflected in this source tree. The code still uses Resend + the Sentry SDK
(no DSN), so neither swap is complete:

- **Transactional email — Resend → AWS SES (planned).** Current code
  (`backend/app/services/email.py`) sends over **Resend SMTP** using the
  verified `xibodev.com` apex sender. The portfolio standard is **AWS SES**
  (eu-west-1 default); because SES is the same backend Resend wraps, this is a
  config-level swap (SMTP creds + sender domain), not a code rewrite. Employed
  is on the **priority SES bulk-verify list** (`equilibria`, `kumbuka`,
  `nagare`, `employed`). Target sender = `noreply@employed.xibodev.com` once
  `employed.xibodev.com` is DKIM-verified on SES; until verified the product
  MUST fall back to `noreply@xibodev.com` (apex, already on Resend) or mail
  bounces. Status: pending SES domain verification. Source:
  `docs/operations/INFRASTRUCTURE.md` (Email — transactional).
- **Error tracking — Sentry → Bugsink on Box 0 (planned).** Covered in
  Observability above. Status: pending DSN provisioning.

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
