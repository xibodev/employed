# Employed — Release Notes

```yaml
last_verified: 2026-06-11T04:50:00Z
verified_by: fix-executor follow-up pass (quality run 2026-06-10_120309)
branch: fix/quality-run-2026-06-10 (uat baseline 00aa899)
```

Claims policy: anything under **UNRELEASED** cites `tested_locally` evidence
(commit + local gate) from `docs/product/FEATURE_REGISTRY.md` §B — **nothing in
that section is live**. Deployed claims appear only under a dated release with a
deploy-run id.

---

## [UNRELEASED] `employed-uat-2026-06-10` — quality-run fix release (pending merge + deploy)

> **STATUS: NOT RELEASED.** Branch `fix/quality-run-2026-06-10` (28 fix commits
> + docs) is local-only — never pushed, never merged. The live UAT on Box 3
> still runs the pre-fix build `uat` @ `00aa899`. Release verdict from
> `release/release-decision.json`: **production promotion NO-GO · continued UAT
> iteration GO.**
>
> **Pre-merge/pre-deploy prerequisites (hard gates):**
> 1. **BL-001 / CARTO-002 — RESOLVED ON BRANCH, pending merge (2026-06-11).**
>    `deploy-uat.yml` now upserts `FRONTEND_BASE_URL`, `NEXT_PUBLIC_APP_URL`,
>    exact-origin `CORS_ORIGINS`, `ENVIRONMENT=uat`, `SENTRY_DSN` (optional
>    `EMPLOYED_UAT_SENTRY_DSN` secret, empty-safe) and `SENTRY_ENVIRONMENT=uat`.
>    Takes effect on the first deploy after merge.
> 2. **BL-002** — UAT origins covered by the BL-001 upsert; operator re-checks
>    only for future envs with different origins.
> 3. Push to `uat` triggers the live deploy — a human 🟡 confirm-first action.

Baseline: `uat` @ `00aa899` · Local gate: ruff PASS · pytest **134/134**
(+51 regression tests over the 83 baseline) · eslint PASS · tsc PASS ·
`next build` PASS (17/17 pages). Top-5 fixes empirically re-verified on a
re-seeded sealed Docker stack (`fix-execution/execution-report.json`).

### Fixed — promotion blockers

- **Admin moderation restored (EMP-026, critical).** `GET /admin/reports` no
  longer 500s on UUID serialization (`548c6b6`; also fixed the same latent bug
  in `POST /reports`/resolve), and the admin dashboard degrades per-panel
  instead of blanking entirely on one failed call (`592a0d4`). Re-verified: 200
  with seeded reports.
- **MX market correctness (EMP-001).** `MarketMiddleware` honors
  `X-Forwarded-Host`, so split-host deploys resolve the right market
  (`e655f74`). Re-verified: `x-market: mx`, Mexico-only listings, Stripe-only
  providers.
- **Registration funnel un-dead-ended (EMP-004).** Verification/reset emails now
  link to frontend pages built from `FRONTEND_BASE_URL` (`2a01442`).
  Re-verified via MailHog capture.
- **Anonymous job posting works (EMP-002+003).** reCAPTCHA secret resolvable;
  both ends agree on the `submit_job` action; bypass honored only in dev/test
  (`0aa4c54`). Re-verified by in-container probe.

### Fixed — security

- Refresh JWT moved out of localStorage into an httpOnly `SameSite=Lax` cookie
  scoped to `/auth` (`9b08eb2`, EMP-006). **Requires exact `CORS_ORIGINS`.**
- Redis-backed rate limits + login lockout, trusted-proxy IP resolution,
  lockout keyed by (email, client IP) to kill the victim-lockout DoS
  (`d176650`, EMP-007+020).
- OAuth account linking requires the provider's verified-email claim; takeover
  attempt → 403 (`2f706fe`+`5ee819e`, EMP-018).
- Moderation gaps closed: non-owners can't read others' non-active listings;
  owner edits of active listings reset to `pending` for re-moderation
  (`4c142ad`, EMP-008).
- Mobile-money webhook replay cache moved to Redis; payload `timestamp` now
  **mandatory** — timestamp-less callbacks 400 (`64b721c`, EMP-019).
  **Contract change**: confirm provider payloads before live integration.
- Poster contact email is now **auth-gated** (EMP-028, decided + implemented
  2026-06-11): anonymous payloads of `/jobs`, `/jobs/featured` and `/jobs/{id}`
  return `contact: null` (nothing in SSR HTML source); signed-in users reveal
  it explicitly on the job detail page, anonymous visitors get a sign-in CTA,
  and URL/WhatsApp apply paths stay public. Policy + reversal path: KL-06.

### Fixed — correctness & UX

- Verified users no longer see a false "pending verification" banner — frontend
  reads snake_case `email_verified` (`3b77958`, EMP-029).
- Malformed verify/reset tokens return 400 instead of 500 (`455abbf`, EMP-025).
- Deactivation notification goes to the job owner, not the acting admin
  (`596d984`, EMP-016).
- Expiry worker records the reason in `status_history`; worker package imports
  without `REDIS_URL` (`d26aa78`+`6a102e9`, EMP-017).
- `is_email_verified` returns False for no-email/no-OAuth ghost rows
  (`bd3fff4`, EMP-022).
- Admin user search added so non-admins can be found and promoted
  (`7bb648d`, EMP-015).

### Fixed — performance

- Auth user lookups use indexed queries instead of full-table scans
  (`db22497`, EMP-005).
- `/jobs` search/filter/pagination/count pushed into SQL (`b14a3c2`, EMP-010).
- Public aliases `/api/jobs` + `/api/featuredJobs` (what the frontend actually
  calls) moved onto the same SQL pushdown with parity + SQL-shape regression
  tests; `/api/featuredJobs` keeps its deterministic newest-first contract
  (CARTO-001 / BL-006, resolved 2026-06-11).

### Fixed — i18n / SEO / config (locales: en, pt, es)

- Auth, account, my-jobs, job-detail, and post-job surfaces localized for pt/es;
  catalogs key-set-synced at 263 keys per locale (`a61af61`, EMP-027).
- All market/robots/sitemap/canonical domains derive from
  `NEXT_PUBLIC_APP_URL`; zero hardcoded domains left in `frontend/src`
  (`a7d1cef`, EMP-013+024).
- API URL + reCAPTCHA site key become runtime config (`window.__ENV` injection)
  — config changes are a restart, not a rebuild (`7982049`, EMP-012).

### Build / test infrastructure

- Backend requirements pinned; `pymongo`/`tqdm`/pytest dropped from the runtime
  image (`5ed6f95`, EMP-021). **Next image build changes the dependency set.**
- ORM index declarations aligned with migrations — autogenerate stops proposing
  duplicates/drops (`be945ac`, EMP-009). No migration shipped.
- E2E suite made trustworthy: locale-aware assertions, QP-decoded MailHog
  bodies, robots/sitemap 200 expectations (`5868453`, TD-001/002/003).
- BFS-003 closed: behavioral Playwright regression for EMP-026b per-panel
  admin degradation (`tests/e2e/regression-admin-panel-degradation.spec.js` —
  stubs `/admin/reports` → 500, asserts jobs/users panels render and only the
  reports panel errors). Requires the running stack, like the journey specs.

### NOT in this release (blocked / deferred)

- **EMP-011** Sentry/uptime provisioning — blocked, external-ops (operator);
  in-repo env schema documented (`c238655`).
- **EMP-014** Stripe-dashboard webhook-URL verification — blocked, external-ops
  (operator); in-repo smoke test pins the route (`dee9a00`).
- **TD-004** frontend component-test foundation — tooling decision (BL-008).

### Deploy-sensitive changes (operator briefing)

- New env names (names only): `FRONTEND_BASE_URL`, `RECAPTCHA_MIN_SCORE`,
  `RECAPTCHA_BYPASS_IN_DEVELOPMENT`, `TRUSTED_PROXY_IPS`, `CORS_ORIGINS`,
  `SENTRY_DSN`, `SENTRY_ENVIRONMENT` — documented in `deploy/.env.example`;
  the deploy-critical subset is **now upserted by `deploy-uat.yml`** (BL-001,
  resolved on branch 2026-06-11).
- EMP-019 webhook contract change (mandatory timestamp) takes effect on deploy.
- Backend image dependency set changes on next build (EMP-021).
- **Deploy-affecting workflow change (BL-001):** `.github/workflows/deploy-uat.yml`
  env-upsert block extended on this branch (operator-authorized). It deploys
  nothing by itself, but the first post-merge push to `uat` applies the new
  env set on Box 3. `deploy/docker-compose.prod.yml` remains unmodified except
  for the pre-existing worker-healthcheck fix.

---

## employed-uat @ `00aa899` — current live UAT baseline (deployed 2026-05-27)

- **Deploy evidence:** GitHub Actions run `26541953900` (`deploy-uat.yml`,
  success, 2026-05-27); live probes 2026-06-11T01:44:01Z — API `/health` 200
  (db/redis ok), frontend 200, `mx` host 200. Registry §A rows.
- Surfaces live: market-localized listings (mz/mx), email/password + Google
  OAuth auth, admin moderation, 90-day expiry worker, Stripe test-mode featured
  payments, mobile-money simulator, robots/sitemap, i18n en/pt/es.
- **This build carries the KL-00 defect set** (admin-moderation outage with
  reports present, MX-serves-MZ, dead verification links, broken anonymous
  posting) — see `KNOWN_LIMITATIONS.md` KL-00. They are fixed in the UNRELEASED
  section above, pending merge + deploy.
