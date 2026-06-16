# Employed Migration Plan — Meteor → FastAPI + Next.js 15 + PostgreSQL

> **Status update (May 2026):** The migration is complete. This document is preserved as historical reference for the rewrite that moved Employed from Meteor to the current FastAPI + Next.js stack.

**Status:** Migration Complete — May 2026
**Scope:** Full rewrite of `employed.co.mz` from Meteor 2.7.1 + MongoDB to the portfolio-standard stack.
**Target:** Drop-in replacement with feature parity, portfolio-consistent infrastructure, and improved SEO.

---

## 1. Source inventory summary

| Layer | Meteor (current) | Count |
|-------|-------------------|-------|
| Collections (data models) | Jobs, Profiles, PaymentIntents, JobReports, Users | 5 |
| Server methods (mutations) | deactivateJob, deleteMine, adminSetJobStatus, adminSetJobStatusBulk, adminGrantRole, adminRevokeRole | 6 |
| Publications (queries) | homeJobs, featuredJobs, jobs, my_jobs, adminJobs, adminUsers, adminJobReports, job, mySponsorState, null-user | 10 |
| REST endpoints | GET /api/jobs, GET /api/featuredJobs, GET /api/me/export | 3 |
| Routes (pages) | home, jobs, myJobs, adminJobs, job, jobNew, jobEdit, legalPrivacy, legalTerms, userAccount, signIn, signUp, forgotPwd, resetPwd, verifyEmail, jobNewAlias | 16 |
| Blaze templates | ~211 template references across client/ | ~30 files |
| Payment adapters | Stripe (checkout+webhooks), M-Pesa (sim+real), e-Mola (sim+real) | 3 |
| Auth | Meteor Accounts + password + OAuth (Google, Facebook, GitHub, Twitter) | 5 providers |
| Tests | 8 unit (Mocha/Chai) + 2 e2e (Playwright) | 10 |
| Total LOC | ~21,000 | 127 files |

---

## 2. Target architecture

```
employed/
├── backend/                    # FastAPI (Python 3.12)
│   ├── apps/api/               # Routers, dependencies, settings
│   ├── modules/
│   │   ├── jobs/               # models, schemas, service, router
│   │   ├── profiles/           # models, schemas, service, router
│   │   ├── payments/           # models, schemas, service, router
│   │   │   ├── stripe.py       # Stripe adapter
│   │   │   ├── mpesa.py        # M-Pesa adapter
│   │   │   └── emola.py        # e-Mola adapter
│   │   ├── reports/            # models, schemas, service, router
│   │   ├── auth/               # JWT + OAuth + password
│   │   └── admin/              # admin endpoints + RBAC
│   ├── shared/
│   │   ├── db/                 # Base, session, migrations (Alembic)
│   │   ├── security/           # bcrypt hashing, JWT, RBAC
│   │   └── middleware/         # rate limiting, logging, CORS
│   ├── workers/                # arq background jobs (cron, cleanup)
│   └── tests/
├── frontend/                   # Next.js 15 (React 19, App Router)
│   ├── app/
│   │   ├── (public)/           # home, jobs, job/[slug], legal/*
│   │   ├── (auth)/             # sign-in, sign-up, forgot-password, etc.
│   │   ├── my/                 # my-jobs, account
│   │   ├── admin/              # admin/jobs, admin/users, admin/reports
│   │   └── api/                # Next.js API routes (if needed)
│   ├── components/             # shared React components
│   └── lib/                    # API client, auth context, utils
├── docker-compose.yml
├── docker-compose.uat.yml
├── Dockerfile.backend
├── Dockerfile.frontend
└── .env.example
```

---

## 3. Data model mapping (MongoDB → PostgreSQL)

### 3.1 jobs → `jobs` table

| Mongo field | Postgres column | Type | Notes |
|-------------|-----------------|------|-------|
| _id | id | UUID PK | |
| title | title | VARCHAR(255) | NOT NULL |
| company | company | VARCHAR(255) | |
| country | country | VARCHAR(2) | 'MZ', 'MX' |
| location | location | VARCHAR(255) | |
| url | url | TEXT | |
| contact | contact | VARCHAR(255) | |
| applyWhatsApp | apply_whatsapp | VARCHAR(20) | |
| jobtype | job_type | ENUM | full_time, part_time, contract, freelance, internship |
| remote | remote | BOOLEAN | |
| salaryMin | salary_min | DECIMAL | |
| salaryMax | salary_max | DECIMAL | |
| salaryCurrency | salary_currency | VARCHAR(3) | |
| salaryPeriod | salary_period | ENUM | hourly, monthly, yearly |
| userId | user_id | UUID FK → users | |
| userName | — | dropped | Denormalized; join on user_id |
| description | description | TEXT | Markdown source |
| htmlDescription | html_description | TEXT | Rendered HTML (or render at read time) |
| status | status | ENUM | draft, pending, active, rejected, expired, filled, deleted |
| featuredThrough | featured_through | TIMESTAMPTZ | |
| featuredChargeHistory | — | moved | → payment_intents table |
| statusHistory | — | moved | → job_status_history table (or JSONB) |
| expiredAt | expired_at | TIMESTAMPTZ | |
| publishedAt | published_at | TIMESTAMPTZ | |
| createdAt | created_at | TIMESTAMPTZ | |
| updatedAt | updated_at | TIMESTAMPTZ | |

Text search: Postgres `tsvector` + GIN index on title + company + description.

### 3.2 experts → `profiles` table

| Mongo field | Postgres column | Type |
|-------------|-----------------|------|
| _id | id | UUID PK |
| userId | user_id | UUID FK → users, UNIQUE |
| name | name | VARCHAR(255) |
| title | title | VARCHAR(255) |
| location | location | VARCHAR(255) |
| description | description | TEXT |
| availableForHire | available_for_hire | BOOLEAN |
| interestedIn | interested_in | TEXT[] (array) |
| contact | contact | VARCHAR(255) |
| url / resumeUrl / githubUrl / linkedinUrl / stackoverflowUrl | urls | JSONB |
| customImageUrl | custom_image_url | TEXT |
| status | status | ENUM |
| createdAt / updatedAt | created_at / updated_at | TIMESTAMPTZ |

### 3.3 paymentIntents → `payment_intents` table

| Mongo field | Postgres column | Type |
|-------------|-----------------|------|
| _id | id | UUID PK |
| jobId | job_id | UUID FK → jobs |
| userId | user_id | UUID FK → users |
| marketKey | market_key | VARCHAR(10) |
| providerKey | provider_key | ENUM (stripe, mpesa, emola) |
| providerRef | provider_ref | VARCHAR(255) |
| status | status | ENUM (pending, settled, failed, refunded, disputed) |
| amount | amount | DECIMAL |
| currency | currency | VARCHAR(3) |
| payerMsisdn | payer_msisdn | VARCHAR(20) |
| payerMsisdnHash | payer_msisdn_hash | VARCHAR(64) |
| extendedThrough | extended_through | TIMESTAMPTZ |
| failureReason | failure_reason | TEXT |
| simulator | simulator | BOOLEAN |
| meta | meta | JSONB |
| createdAt / updatedAt / settledAt | created_at / updated_at / settled_at | TIMESTAMPTZ |

### 3.4 jobReports → `job_reports` table

| Mongo field | Postgres column | Type |
|-------------|-----------------|------|
| _id | id | UUID PK |
| jobId | job_id | UUID FK → jobs |
| reason | reason | ENUM |
| details | details | TEXT |
| reporterIpHash | reporter_ip_hash | VARCHAR(64) |
| reporterUserId | reporter_user_id | UUID FK → users (nullable) |
| resolution | resolution | ENUM (nullable) |
| resolvedBy | resolved_by | UUID FK → users (nullable) |
| resolvedAt | resolved_at | TIMESTAMPTZ |
| createdAt | created_at | TIMESTAMPTZ |

### 3.5 Meteor.users → `users` table

| Mongo field | Postgres column | Type |
|-------------|-----------------|------|
| _id | id | UUID PK |
| emails[0].address | email | VARCHAR(255) UNIQUE |
| emails[0].verified | email_verified | BOOLEAN |
| profile.name | display_name | VARCHAR(255) |
| services.password.bcrypt | password_hash | VARCHAR(255) |
| roles | — | → user_roles join table |
| createdAt | created_at | TIMESTAMPTZ |
| updatedAt | updated_at | TIMESTAMPTZ |

### 3.6 New table: `user_roles`

| Column | Type |
|--------|------|
| user_id | UUID FK → users |
| role | ENUM (user, admin) |
| PK | (user_id, role) |

---

## 4. API mapping (Meteor methods + publications → FastAPI endpoints)

### 4.1 Public endpoints

| Current | New endpoint | Method | Notes |
|---------|-------------|--------|-------|
| pub: homeJobs | `GET /api/v1/jobs?home=true` | GET | Paginated, filtered |
| pub: featuredJobs | `GET /api/v1/jobs/featured` | GET | Random sample |
| pub: jobs (browse) | `GET /api/v1/jobs?country=MZ&q=...&page=1` | GET | Full-text search, pagination |
| pub: job (detail) | `GET /api/v1/jobs/{slug}` | GET | By slug, increment views |
| REST: /api/jobs | `GET /api/v1/jobs` | GET | Same as above (consolidate) |
| REST: /api/featuredJobs | `GET /api/v1/jobs/featured` | GET | Same as above |

### 4.2 Authenticated user endpoints

| Current | New endpoint | Method |
|---------|-------------|--------|
| pub: my_jobs | `GET /api/v1/my/jobs` | GET |
| method: jobs.create (implicit) | `POST /api/v1/my/jobs` | POST |
| route: jobEdit | `PUT /api/v1/my/jobs/{id}` | PUT |
| method: deactivateJob | `POST /api/v1/my/jobs/{id}/deactivate` | POST |
| method: jobs.deleteMine | `DELETE /api/v1/my/jobs/{id}` | DELETE |
| pub: mySponsorState | `GET /api/v1/my/jobs/{id}/sponsor-state` | GET |
| REST: /api/me/export | `GET /api/v1/my/export` | GET |

### 4.3 Admin endpoints

| Current | New endpoint | Method |
|---------|-------------|--------|
| pub: adminJobs | `GET /api/v1/admin/jobs` | GET |
| pub: adminUsers | `GET /api/v1/admin/users` | GET |
| pub: adminJobReports | `GET /api/v1/admin/reports` | GET |
| method: adminSetJobStatus | `POST /api/v1/admin/jobs/{id}/status` | POST |
| method: adminSetJobStatusBulk | `POST /api/v1/admin/jobs/bulk-status` | POST |
| method: adminGrantRole | `POST /api/v1/admin/users/{id}/roles` | POST |
| method: adminRevokeRole | `DELETE /api/v1/admin/users/{id}/roles/{role}` | DELETE |

### 4.4 Auth endpoints

| Current | New endpoint | Method |
|---------|-------------|--------|
| Accounts.createUser | `POST /api/v1/auth/register` | POST |
| Meteor.loginWithPassword | `POST /api/v1/auth/login` | POST |
| Accounts.forgotPassword | `POST /api/v1/auth/forgot-password` | POST |
| Accounts.resetPassword | `POST /api/v1/auth/reset-password` | POST |
| Accounts.verifyEmail | `POST /api/v1/auth/verify-email` | POST |
| loginWithGoogle/Facebook/etc | `GET /api/v1/auth/oauth/{provider}` | GET |

### 4.5 Payment endpoints

| Current | New endpoint | Method |
|---------|-------------|--------|
| Stripe checkout session | `POST /api/v1/payments/stripe/checkout` | POST |
| Stripe webhook | `POST /api/v1/payments/stripe/webhook` | POST |
| M-Pesa initiate | `POST /api/v1/payments/mpesa/initiate` | POST |
| M-Pesa callback | `POST /api/v1/payments/mpesa/callback` | POST |
| e-Mola initiate | `POST /api/v1/payments/emola/initiate` | POST |
| e-Mola callback | `POST /api/v1/payments/emola/callback` | POST |

---

## 5. Frontend page mapping (Blaze → Next.js 15 App Router)

| Meteor route | Next.js path | Type | Key components |
|-------------|-------------|------|----------------|
| home | `app/(public)/page.tsx` | SSR | Hero, featured jobs strip, search |
| jobs | `app/(public)/jobs/page.tsx` | SSR | Search + filter + paginated list |
| job | `app/(public)/jobs/[slug]/page.tsx` | SSR | Job detail, JSON-LD, apply CTA |
| jobNew | `app/my/jobs/new/page.tsx` | Client | Job form (rich text editor) |
| jobEdit | `app/my/jobs/[id]/edit/page.tsx` | Client | Job form (prefilled) |
| myJobs | `app/my/jobs/page.tsx` | Client | User's job listings + status |
| userAccount | `app/my/account/page.tsx` | Client | Profile, password, OAuth |
| adminJobs | `app/admin/jobs/page.tsx` | Client | Moderation queue |
| adminUsers | `app/admin/users/page.tsx` | Client | User management |
| signIn | `app/(auth)/sign-in/page.tsx` | Client | Email + OAuth buttons |
| signUp | `app/(auth)/sign-up/page.tsx` | Client | Registration |
| forgotPwd | `app/(auth)/forgot-password/page.tsx` | Client | |
| resetPwd | `app/(auth)/reset-password/page.tsx` | Client | |
| verifyEmail | `app/(auth)/verify-email/page.tsx` | Client | |
| legalPrivacy | `app/(public)/privacy/page.tsx` | Static | |
| legalTerms | `app/(public)/terms/page.tsx` | Static | |

### Shared components to build

- `<JobCard>` — used in listings, featured strip, my-jobs
- `<JobForm>` — create/edit with rich text (Tiptap or similar)
- `<SearchFilters>` — country, job type, remote, salary, text
- `<Pagination>` — cursor or offset
- `<Header>` — nav, auth state, market switcher (mz/mx)
- `<Footer>` — links, legal
- `<FeaturedStrip>` — horizontal scroll of featured jobs
- `<AdminStatusActions>` — approve/reject/bulk actions
- `<PaymentCheckout>` — Stripe/M-Pesa/e-Mola selector
- `<OAuthButtons>` — Google, Facebook, GitHub, Twitter
- `<SEOHead>` — per-page og: tags, JSON-LD

---

## 6. Background workers (cron → arq)

| Meteor cron | arq job | Schedule |
|-------------|---------|----------|
| Expire old jobs (90 days) | `expire_stale_jobs` | Daily 02:00 |
| M-Pesa/e-Mola polling | `poll_pending_payments` | Every 30s |
| Featured expiration check | `expire_featured` | Hourly |
| Cleanup unverified accounts | `cleanup_unverified` | Daily 03:00 |

---

## 7. Migration execution plan

### Phase 1 — Backend (can parallelize across 3 agents)

**Agent 1: Database + Models**
- [ ] Create SQLAlchemy models for all 6 tables + enums
- [ ] Create Alembic initial migration
- [ ] Write seed script (dev data)
- [ ] Set up Postgres full-text search indexes

**Agent 2: API Layer**
- [ ] FastAPI app scaffold (settings, dependencies, middleware)
- [ ] Auth module (JWT, bcrypt, OAuth adapters, register/login/verify/reset)
- [ ] RBAC middleware (user vs admin)
- [ ] Jobs module (CRUD, search, pagination, slug generation)
- [ ] Profiles module (CRUD)
- [ ] Reports module (CRUD, admin resolve)
- [ ] Admin module (status changes, bulk ops, role management)
- [ ] Data export endpoint

**Agent 3: Payments + Workers**
- [ ] Payment intents module (model, schemas, service)
- [ ] Stripe adapter (checkout session creation, webhook handler)
- [ ] M-Pesa adapter (initiate, callback, simulator mode)
- [ ] e-Mola adapter (initiate, callback, simulator mode)
- [ ] arq worker setup (cron jobs: expire, poll, cleanup)
- [ ] Sentry integration
- [ ] Health + readiness endpoints

### Phase 2 — Frontend (can parallelize across 2 agents)

**Agent 4: Public pages + SEO**
- [ ] Next.js 15 scaffold (App Router, Tailwind CSS)
- [ ] Layout (Header, Footer, market switcher)
- [ ] Home page (SSR, featured strip, search)
- [ ] Jobs browse page (SSR, search + filters + pagination)
- [ ] Job detail page (SSR, JSON-LD, og: tags, apply CTA)
- [ ] Legal pages (static)
- [ ] Sitemap + robots.txt
- [ ] PWA manifest (port from existing)

**Agent 5: Auth + Dashboard pages**
- [ ] Auth pages (sign-in, sign-up, forgot/reset password, verify email)
- [ ] OAuth buttons (Google, Facebook, GitHub, Twitter)
- [ ] My Jobs page (list, status, deactivate, delete)
- [ ] Job create/edit form (rich text editor)
- [ ] Featured checkout flow (Stripe/M-Pesa/e-Mola selector)
- [ ] Account settings page
- [ ] Admin: jobs moderation queue
- [ ] Admin: users management
- [ ] Admin: reports queue
- [ ] reCAPTCHA v3 integration

### Phase 3 — Infrastructure + Integration (1 agent, after Phase 1-2)

**Agent 6: Docker + CI + Tests**
- [ ] Dockerfile.backend (multi-stage, non-root)
- [ ] Dockerfile.frontend (multi-stage)
- [ ] docker-compose.yml (backend + frontend + postgres + redis + mailhog)
- [ ] docker-compose.uat.yml
- [ ] .env.example
- [ ] GitHub Actions CI (lint + type-check + tests + Docker build)
- [ ] deploy-uat.yml (SSH → Box A)
- [ ] Port block assignment: 3300–3319 (per INFRASTRUCTURE.md)
- [ ] Caddy config for employed.xibodev.com

### Phase 4 — Tests + Data Migration (1 agent, after Phase 3)

**Agent 7: Tests + Migration Script**
- [ ] Backend unit tests (pytest) — target: match or exceed 88 existing
- [ ] Playwright e2e tests (port existing journeys.spec.js + smoke.spec.js)
- [ ] MongoDB → PostgreSQL data migration script (if any real data exists)
- [ ] Verify all 16 routes render correctly
- [ ] Verify all 3 payment flows work in simulator mode
- [ ] Verify admin moderation workflow end-to-end

---

## 8. Parallelization strategy

```
Day 1 (session 1):
  ├── Agent 1: Database + Models ─────────────┐
  ├── Agent 2: API Layer ─────────────────────┤── Backend complete
  └── Agent 3: Payments + Workers ────────────┘
                                               ↓
Day 1-2 (session 2):                     API contracts ready
  ├── Agent 4: Public pages + SEO ────────────┐
  └── Agent 5: Auth + Dashboard ──────────────┤── Frontend complete
                                               ↓
Day 2 (session 3):
  ├── Agent 6: Docker + CI ───────────────────┤── Infrastructure
  └── Agent 7: Tests + Migration ─────────────┘── Verification

Total: 2-3 sessions, 7 parallel agents across 3 phases
```

---

## 9. Risk register

| Risk | Mitigation |
|------|------------|
| Blaze → React is the biggest effort | Prioritize SSR public pages first (SEO critical); admin pages can be simpler |
| OAuth provider setup | Reuse existing OAuth app credentials; just change redirect URIs |
| Payment webhook URLs change | Update Stripe dashboard + M-Pesa/e-Mola config post-deploy |
| Data loss during migration | Keep Meteor app running until new app is UAT-verified; no data migration if starting fresh |
| CSS/styling regression | Use Tailwind; match existing Bootstrap look roughly, don't pixel-match |
| SEO ranking disruption | Maintain same URL slugs; add 301 redirects for any changed paths |

---

## 10. What stays the same

- Domain: employed.co.mz (mz.employed.co.mz / mx.employed.co.mz)
- Port block: 3300–3319
- Box A deployment target
- Stripe + M-Pesa + e-Mola payment providers
- UAT subdomain: employed.xibodev.com
- reCAPTCHA v3
- Sentry error tracking
- Same job/profile data schema (semantically)

## 11. What changes

| Before | After |
|--------|-------|
| Meteor 2.7.1 | FastAPI 0.115+ |
| MongoDB | PostgreSQL 16 |
| Blaze templates | Next.js 15 / React 19 |
| Meteor pub/sub | REST API + SWR/React Query |
| Meteor Accounts | JWT + bcrypt + OAuth |
| Mocha/Chai | pytest + Playwright |
| Iron Router | Next.js App Router |
| SyncedCron | arq + Redis |
| accounts-password | Custom auth module |
