# Employed — Feature Registry

```yaml
last_verified: 2026-06-11T04:50:00Z
verified_by: fix-executor follow-up pass (quality run 2026-06-10_120309)
branch: fix/quality-run-2026-06-10 (uat baseline 00aa899)
live_uat_probe: https://api.employed.xibodev.com/health -> 200 {status ok, db ok, redis ok} at 2026-06-11T01:44:01Z
```

Every row carries a status from the 8-status machine and the observable evidence
backing it. Statuses: `planned → in_progress → implemented → tested_locally →
uat_ready → deployed_to_uat`, plus terminal/side states `blocked`, `deprecated`.

**Read this first:** the live UAT on Box 3 still runs the **pre-fix** build
(`uat` @ `00aa899`, deploy run `26541953900`, 2026-05-27). The 28 fixes from
quality run `2026-06-10_120309` exist only on the local, unpushed branch
`fix/quality-run-2026-06-10` and are therefore **`tested_locally`, not
`deployed_to_uat`**. Section A statuses describe the live build; Section B
statuses describe the in-flight release.

---

## A. Product features (live UAT build — `uat` @ `00aa899`)

Deploy evidence for every `deployed_to_uat` row below: GitHub Actions deploy run
**`26541953900`** (2026-05-27, `deploy-uat.yml`, success) + live HTTPS probes at
**2026-06-11T01:44:01Z** (`api.employed.xibodev.com/health` 200 with db/redis ok;
`employed.xibodev.com` 200; `mx.employed.xibodev.com` 200). Note: the product is
**not yet Atlas-registered** (no `atlas.json`) — reachability was
verified by direct probe instead of an Atlas API record (finding BFS-005).

| ID | Feature | Status | Last activity | Owner | Evidence / defects on the live build |
|---|---|---|---|---|---|
| EMP-F-001 | Market-localized public job listings (`mz.*` / `mx.*` hostname → market context, market-scoped pricing/providers) | `deployed_to_uat` | 2026-05-27 deploy | engineering | Crawl 33/33 pages clean across default/mz/mx hosts. **Live defect EMP-001:** behind the split API host, MX serves MZ jobs/MZN pricing (fix `e655f74`, `tested_locally`). |
| EMP-F-002 | Job posting — authenticated + anonymous with reCAPTCHA v3 | `deployed_to_uat` | 2026-05-27 deploy | engineering | Headed tours pass for authed posting. **Live defect EMP-002/003:** anonymous posting always 400s (secret unreadable + action mismatch; fix `0aa4c54`, `tested_locally`). |
| EMP-F-003 | Email/password auth: register, email verification, login, forgot/reset password | `deployed_to_uat` | 2026-05-27 deploy | engineering | Funnel exercised E2E on sealed stack. **Live defects:** verification/reset links 405 dead-end (EMP-004, fix `2a01442`); verified users shown "pending verification" (EMP-029, fix `3b77958`); malformed tokens 500 (EMP-025, fix `455abbf`) — all `tested_locally`. |
| EMP-F-004 | Google OAuth sign-in (only configured OAuth provider) | `deployed_to_uat` | 2026-05-27 deploy | engineering | Live callback at `api.employed.xibodev.com/auth/oauth/google/callback`. **Live defect EMP-018:** account linking skips the provider verified-email claim (fix `2f706fe`+`5ee819e`, `tested_locally`). |
| EMP-F-005 | Admin moderation workflow (`pending → active → filled/inactive`), report review, job/user admin | `deployed_to_uat` | 2026-05-27 deploy | engineering | Headed admin tour reached all panels. **CRITICAL live defect EMP-026:** with ≥1 report in DB, `GET /admin/reports` 500s and the whole admin UI blanks — moderation dead (fixes `548c6b6`+`592a0d4`, `tested_locally`). |
| EMP-F-006 | 90-day listing expiry worker (arq) | `deployed_to_uat` | 2026-05-27 deploy | engineering | Positive empirical evidence: worker transitioned a >90-day job during the 2026-06-10 run (`uat/stack-health-resume.json`). Branch adds `status_history` reason (EMP-017). |
| EMP-F-007 | Featured-job payments via Stripe (test mode) | `deployed_to_uat` | 2026-05-27 deploy | engineering | Test keys configured; webhook mounted at `POST /webhooks/_stripe/webhook` (503-not-404 verified on sealed stack). Dashboard-URL verification pending (EMP-014, `blocked`). Live keys absent — test mode only. |
| EMP-F-008 | Featured-job payments via M-Pesa / e-Mola (MZ mobile money) | `deployed_to_uat` (simulator mode only) | 2026-05-27 deploy | engineering | Webhook surfaces deployed; **simulator mode** — no webhook secrets/sandbox credentials configured (see KNOWN_LIMITATIONS). Branch makes callback `timestamp` mandatory (EMP-019, contract change). |
| EMP-F-009 | Public read API + health endpoints | `deployed_to_uat` | 2026-05-27 deploy | engineering | `GET /health` 200 (db/redis ok) probed 2026-06-11T01:44:01Z; UptimeRobot monitors `803170467` (frontend) + `803177488` (API) UP. Perf caveat CARTO-001 (live build filters `/api/jobs` aliases in Python) fixed on the branch — see CARTO-001 row in §B. |
| EMP-F-010 | i18n en/pt/es with per-market defaults (mx→es, mz→pt) | `deployed_to_uat` | 2026-05-27 deploy | engineering | Market-default locale serving verified by crawl. **Live gap EMP-027:** auth/account/my-jobs/job-detail/post-job surfaces English-only on pt/es (localization vision score 2.61/5); full catalogs (263 keys/locale) `tested_locally` (`a61af61`). |
| EMP-F-011 | SEO: robots.txt + sitemap.xml | `deployed_to_uat` | 2026-05-27 deploy | engineering | Both serve 200 (new since prior suite). **Live defect EMP-013/024:** UAT domain hardcoded in source — wrong-for-prod SEO (fix `a7d1cef` derives from `NEXT_PUBLIC_APP_URL`, `tested_locally`). |
| EMP-F-012 | Account management + "my jobs" dashboard | `deployed_to_uat` | 2026-05-27 deploy | engineering | Headed persona tours 10/10, pages 200, auth injection OK. |
| EMP-F-013 | Community abuse reports on listings | `deployed_to_uat` | 2026-05-27 deploy | engineering | Report submission works; reviewing them trips EMP-026 on the live build (see EMP-F-005). |
| EMP-F-014 | Transactional email via Resend SMTP | `deployed_to_uat` | 2026-05-27 deploy | operator | Live sender `noreply@xibodev.com` (apex — Employed domain not Resend-verified; see KNOWN_LIMITATIONS). MailHog-verified on sealed stack. |
| EMP-F-015 | Production brand domain `employed.co.mz` | `blocked` | 2026-05-28 (SERVICES.md audit) | operator | Public DNS NXDOMAIN, no Cloudflare zone. Blocked on ownership/delegation resolution — do not add prod DNS/Caddy routes until resolved. |
| EMP-F-016 | Observability: Sentry error tracking | `blocked` | 2026-06-10 (`c238655` env-schema docs) | operator | Backend SDK wired (DSN-gated `init_sentry()`); **no Sentry project/DSN provisioned** (org `nmtss`, targets `employed-api`/`employed-frontend`). Frontend SDK not added (dependency decision). External-ops blocker EMP-011. |
| EMP-F-017 | Meteor/Mongo legacy (historical migration utilities + docs) | `deprecated` | 2026-06-10 (`5ed6f95`) | engineering | Reference-only. EMP-021 removed `pymongo`/`tqdm` from the runtime image on the fix branch. |

## B. In-flight release `employed-uat-2026-06-10` (branch `fix/quality-run-2026-06-10`, unmerged/unpushed)

Status basis for `tested_locally`: final gate green on 2026-06-10 — ruff PASS ·
pytest **134/134** (baseline 83; +51 regression tests) · eslint PASS · tsc PASS ·
`next build` PASS (17/17 pages) — plus empirical re-verification of the top-5
fixes on a re-seeded sealed stack (`fix-execution/execution-report.json`).
**None of these rows may move to `uat_ready`/`deployed_to_uat` until the branch
is merged, BL-001 (CARTO-002 deploy-env upsert) lands, and a green UAT deploy
run exists.**

| ID | Title | Status | Last activity (commit) | Owner | Evidence |
|---|---|---|---|---|---|
| EMP-026a | Fix `GET /admin/reports` 500 (UUID → str serialization) | `tested_locally` | 2026-06-10 `548c6b6` | engineering | pytest test_admin 10 passed + regression test + empirical 200 with seeded reports |
| EMP-026b | Admin dashboard degrades per-panel instead of blanking | `tested_locally` | 2026-06-11 (BFS-003 regression spec added) | engineering | tsc/eslint/build + behavioral Playwright regression `tests/e2e/regression-admin-panel-degradation.spec.js` (stub-500 reports, jobs/users still render); spec parses via `--list`, execution needs the live stack (post-merge suite re-run) |
| EMP-001 | MarketMiddleware honors `X-Forwarded-Host` | `tested_locally` | 2026-06-10 `e655f74` | engineering | 4 regression tests + empirical x-market/countries/providers checks |
| EMP-004 | Email links target frontend pages (`FRONTEND_BASE_URL`) | `tested_locally` | 2026-06-10 `2a01442` | engineering | 3 regression tests + MailHog-captured frontend link |
| EMP-002+003 | reCAPTCHA secret resolvable + `submit_job` action contract | `tested_locally` | 2026-06-10 `0aa4c54` | engineering | env/settings + action-contract tests + in-container probe |
| EMP-029 | Read snake_case `email_verified` from API payloads | `tested_locally` | 2026-06-10 `3b77958` | engineering | tsc/eslint |
| EMP-025 | 400 (not 500) for malformed verify/reset tokens | `tested_locally` | 2026-06-10 `455abbf` | engineering | garbage-token regressions + empirical 400 |
| EMP-008 | Close moderation gaps on job reads / owner edits | `tested_locally` | 2026-06-10 `4c142ad` | engineering | authz-matrix + status-reset tests (residual: admin-edit ownership transfer → BL-009) |
| EMP-005 | Indexed auth user lookups (no full-table scans) | `tested_locally` | 2026-06-10 `db22497` | engineering | query-shape test asserting no unfiltered SELECT |
| EMP-007+020 | Redis rate limits + lockout, trusted-proxy IP, de-DoS lockout key | `tested_locally` | 2026-06-10 `d176650` | engineering | spoofed-XFF / shared-store / victim-lockout tests |
| EMP-006 | Refresh JWT moved to httpOnly cookie (no localStorage) | `tested_locally` | 2026-06-10 `9b08eb2` | engineering | cookie-lifecycle tests; **operator prereq:** exact `CORS_ORIGINS` per env (BL-002) |
| EMP-027 | Localize auth/account/my-jobs/job-detail/post-job (pt/es) | `tested_locally` | 2026-06-10 `a61af61` | engineering | catalog key-set sync (263 keys/locale) + build green; residuals → BL-015 |
| EMP-013+024 | All market/robots/sitemap domains from `NEXT_PUBLIC_APP_URL` | `tested_locally` | 2026-06-10 `a7d1cef` | engineering | grep gate: zero hardcoded domains in `frontend/src` |
| EMP-012 | Runtime config for API URL + reCAPTCHA site key | `tested_locally` | 2026-06-10 `7982049` | engineering | tsc/eslint/build; restart-not-rebuild verified by compose design |
| EMP-015 | Admin user search (find non-admins to promote) | `tested_locally` | 2026-06-10 `7bb648d` | engineering | 3 search regression tests |
| EMP-010 | `/jobs` search/filter/pagination/count pushed into SQL | `tested_locally` | 2026-06-10 `b14a3c2` | engineering | SQL-shape + parity tests; public aliases covered by the follow-up CARTO-001 row below |
| CARTO-001 | Public aliases `/api/jobs` + `/api/featuredJobs` on the EMP-010 SQL pushdown | `tested_locally` | 2026-06-11 (this pass) | engineering | Shared `_job_query_pushdown` reuse; parity (market/active/90-day/order/featured) + SQL-shape (LIMIT/COUNT) tests in `tests/test_public_api.py`; closes BL-006 / KL-10 on branch |
| EMP-016 | Deactivation notification goes to the job owner | `tested_locally` | 2026-06-10 `596d984` | engineering | owner-notification + self-deactivation tests |
| EMP-017 | Expiry reason in `status_history`; worker importable w/o `REDIS_URL` | `tested_locally` | 2026-06-10 `d26aa78`+`6a102e9` | engineering | new `tests/test_workers.py` |
| EMP-018 | OAuth linking requires provider verified-email claim | `tested_locally` | 2026-06-10 `2f706fe`+`5ee819e` | engineering | takeover-rejection (403) + verified-claim link tests |
| EMP-019 | Redis-backed webhook replay cache; mandatory payload timestamp | `tested_locally` | 2026-06-10 `64b721c` | engineering | missing-timestamp 400 + shared-store tests; **contract change** → BL-007 |
| EMP-021 | Pinned backend requirements; migration/test deps out of image | `tested_locally` | 2026-06-10 `5ed6f95` | engineering | local image build: pins resolve, pymongo/tqdm/pytest absent |
| EMP-022 | `is_email_verified` False for no-email/no-OAuth rows | `tested_locally` | 2026-06-10 `bd3fff4` | engineering | ghost-row/oauth-map/legacy-column tests |
| EMP-009 | ORM index declarations aligned with migrations | `tested_locally` | 2026-06-10 `be945ac` | engineering | metadata introspection asserts name parity |
| EMP-023 | SERVICES.md auth/observability refresh | `implemented` | 2026-06-15 (cleanse) | operator | `SERVICES.md` is in-repo and committable; refreshed in the 2026-06-15 self-contained cleanse |
| EMP-011 | Sentry/uptime provisioning | `blocked` (external-ops) | 2026-06-10 `c238655` (in-repo env-schema part) | operator | Provisioning + redeploy are operator actions; see BL-003 |
| EMP-014 | Stripe dashboard webhook-URL verification | `blocked` (external-ops) | 2026-06-10 `dee9a00` (in-repo smoke test) | operator | Dashboard check is an operator action; see BL-004 |
| EMP-028 | Poster contact email auth-gated (anonymous payloads omit it; explicit signed-in reveal + sign-in CTA) | `tested_locally` | 2026-06-11 (this pass) | engineering | Operator authorized acting on the open decision; regression tests in `tests/test_jobs.py`; policy + reversal path in KL-06; closes BL-005 |
| TD-001 | Locale-aware E2E assertions | `tested_locally` | 2026-06-10 `5868453` | engineering | `playwright test --list` parses 52 tests; i18n helper unit-checked |
| TD-002 | QP-decoded MailHog bodies in E2E | `tested_locally` | 2026-06-10 `5868453` | engineering | QP decoder unit-checked (soft-break JWT reassembles) |
| TD-003 | robots/sitemap E2E expectations → 200 + content | `tested_locally` | 2026-06-10 `5868453` | engineering | confirmed against `next build` output |
| TD-004 | Frontend component-test foundation | `blocked` (tooling decision) | 2026-06-10 (backend portions landed in owning items) | operator | Runner choice (vitest/RTL) deferred to operator; see BL-008 |

Execution-report totals (against the 33-item plan; some findings consolidated
into combined commits): **28 applied · 2 blocked (external-ops) · 1 partial ·
1 skipped (product decision) · 0 failed**.

---

## C. Hiring-platform evolution (multi-tenant-hiring-platform spec)

Trust-centric, integration-ready hiring platform layered on the job board
(*"more than a job board, less than a heavy ATS"*). Implemented across the
backend (Alembic migrations `003`–`005`; new models, services, and routers) and
the frontend tenant/hiring surfaces. Status `implemented` = code is present on
the working tree with spec property/example tests; **not** independently
re-verified against a live build in this pass. See `docs/product/POSITIONING.md`,
`USER_TYPES_AND_JOURNEYS.md`, and the architecture bundle.

| ID | Feature | Status | Owner | Evidence / notes |
|---|---|---|---|---|
| MTH-F-001 | Multi-tenancy: `Company` + `Membership`, owner-on-create, invite/accept/suspend, domain auto-membership | `implemented` | engineering | `models/company.py`,`membership.py`; `services/companies.py`,`memberships.py`; `routers/companies.py`,`memberships.py` |
| MTH-F-002 | Two-layer permission-based RBAC (platform + tenant roles, `PERMISSION_CATALOG`) | `implemented` | engineering | `services/rbac.py`; guards across new routers |
| MTH-F-003 | Verification state machine + composable trust badges; company domain verification (DNS TXT / member email) | `implemented` | engineering | `services/verification.py`,`trust.py`; `routers/verification.py` |
| MTH-F-004 | Publication moderation (block/unpublish/mark-review/verify) + append-only audit trail | `implemented` | engineering | `routers/verification.py`; `services/audit.py`; `models/audit_log.py` |
| MTH-F-005 | Version-controlled JSON Resume profiles + server-side PDF resume export (arq) | `implemented` | engineering | `services/profiles_versioning.py`,`resume_templates.py`; `workers/tasks.py#render_resume_pdf`; `routers/profiles.py` versions |
| MTH-F-006 | First-class `Application` entity, email template, recruiter list+kanban pipeline | `implemented` | engineering | `models/application.py`; `services/applications.py`,`application_email.py`; `routers/applications.py` |
| MTH-F-007 | Outbound webhooks (`job.published`,`application.created`,`application.status_changed`) with bounded backoff retry | `implemented` | engineering | `services/webhooks.py`; `workers/tasks.py#deliver_webhook`; `routers/webhooks_admin.py` |
| MTH-F-008 | Standard schemas + `external_refs` + versioned `/export/v1` API | `implemented` | engineering | `services/export.py`,`external_refs.py`; `routers/export_api.py` |
| MTH-F-009 | Reversible data migrations: legacy admins → `platform_super_admin`; company profiles → companies; `status_history` → audit | `implemented` | engineering | `alembic/versions/004_migrate_admins.py`,`005_migrate_legacy_profiles_and_jobs.py` |
| MTH-F-010 | Frontend tenant context + hiring surfaces (dashboard, members, verification, applications) | `implemented` | engineering | `frontend/src/lib/tenant.ts`; new App Router segments; lint/typecheck + tests outstanding → BACKLOG MTH-001 |

---

## Status-evidence rules (how this registry stays defensible)

- `deployed_to_uat` requires a deploy-run id **and** a live reachability check.
- `tested_locally` requires a green local gate plus the cited commit(s).
- `blocked` rows must name the blocker and its owner.
- Any commit referencing a feature ID absent from this registry is a
  documentation-drift finding.
- Steward artefacts for this pass:
  `.quality-run/results/2026-06-10_120309/backlog-steward/` (untracked).
