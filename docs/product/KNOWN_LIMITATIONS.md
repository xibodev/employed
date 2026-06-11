# Employed — Known Limitations

```yaml
last_verified: 2026-06-11T04:50:00Z
verified_by: fix-executor follow-up pass (quality run 2026-06-10_120309)
branch: fix/quality-run-2026-06-10 (uat baseline 00aa899)
```

What a user, operator, or reviewer will observe today and why. Each limitation
links to the backlog item that removes it. "Live UAT" = Box 3 running `uat` @
`00aa899` (deploy run `26541953900`, 2026-05-27) — the 2026-06-10 fix branch is
**not deployed**.

---

## KL-00 — Live UAT still runs the pre-fix build (release-gating)

Until `fix/quality-run-2026-06-10` merges and deploys (after BL-001/BL-002), the
live UAT exhibits every defect the quality run found, including:

- **Admin moderation outage (critical, EMP-026):** with ≥1 abuse report in the
  DB, `GET /admin/reports` 500s and the entire admin UI blanks — no approvals
  possible via UI.
- **MX market serves MZ content (EMP-001):** behind the split API host
  (`api.employed.xibodev.com`), `mx.*` shows Mozambique jobs and MZN pricing.
- **Registration funnel dead-end (EMP-004):** verification/reset email links
  target POST-only API routes → 405 on click.
- **Anonymous job posting always fails (EMP-002/003):** reCAPTCHA secret
  unreadable + action contract mismatch → 400.
- Partial pt/es localization on auth/account/my-jobs/job-detail/post-job
  surfaces (EMP-027); verified users see a "pending verification" banner
  (EMP-029); malformed verify/reset tokens 500 (EMP-025).

All fixes are `tested_locally` on the unmerged branch (registry §B).
**Remove via:** merge + deploy of release `employed-uat-2026-06-10`
(prerequisites BL-001, BL-002).

## KL-01 — No error tracking (Sentry wired, not provisioned)

Backend SDK is in place (`init_sentry()`, DSN-gated no-op) but no Sentry
project/DSN exists (org `nmtss`); frontend SDK not added at all. Production
errors would be invisible — the EMP-026 500 was only caught because the quality
run scraped container logs. **Remove via:** BL-003 (operator).

## KL-02 — No New Relic / APM

Agents not installed on API, frontend, or worker. Only UptimeRobot
(`803170467` frontend, `803177488` API `/health`) provides external monitoring.
**Remove via:** BL-018 (operator).

## KL-03 — Brand domain `employed.co.mz` is unrouted

Public DNS is NXDOMAIN; no Cloudflare zone. All traffic is on the
`*.employed.xibodev.com` UAT subdomains. No production environment exists.
**Remove via:** BL-017 (blocked on ownership/delegation).

## KL-04 — Mobile money (M-Pesa / e-Mola) is simulator-mode only

No webhook secrets or sandbox credentials configured; absence of
`MPESA_WEBHOOK_SECRET` / `EMOLA_WEBHOOK_SECRET` means simulator mode. No real
mobile-money payment has ever been processed. Additionally, after the fix
branch deploys, callbacks **without a `timestamp` field are rejected with 400**
(EMP-019 contract change) — confirm provider payloads before going live.
**Remove via:** BL-007 then BL-019 (operator).

## KL-05 — Email sender rides the apex domain

Transactional email sends as `Employed <noreply@xibodev.com>` via Resend SMTP;
`employed.xibodev.com` is not Resend-verified, and an `employed.co.mz` sender is
deferred until `.mz` DNS exists (KL-03). **Remove via:** BL-016 (operator).

## KL-06 — Poster contact email is visible to anonymous visitors (open product decision)

The public job-detail page shows the poster's contact email to anonymous
visitors, while the public API omits it — an inconsistent exposure policy. This
is also how candidates apply today, so it was deliberately **not** changed
unilaterally (EMP-028 skipped as a product decision). **Resolve via:** BL-005.

## KL-07 — Stripe is test-mode only

Test keys configured; live keys absent. The Stripe-dashboard webhook URL has not
been verified against the mounted `/webhooks/_stripe/webhook` path (EMP-014).
**Remove via:** BL-004 + live keys before real payments (🔴-tier action).

## KL-08 — Localization residuals (post-EMP-027)

Even after the fix branch deploys: API-origin error detail strings remain
English; the admin UI is not localized; job-type/currency/period option labels
stay canonical API values. Locales are en/pt/es. **Remove via:** BL-015.

## KL-09 — No frontend component tests

The frontend ships with zero unit/component tests; the gate relies on
eslint/tsc/build plus E2E. EMP-026b's per-panel degradation is validated by
types/build only — the stub-500 Playwright check has not run (finding BFS-003).
**Remove via:** BL-008.

## KL-10 — Public listing aliases are unoptimized (CARTO-001) — resolved on branch, pending deploy

**Fixed on `fix/quality-run-2026-06-10` (2026-06-11, BL-006):** `/api/jobs` and
`/api/featuredJobs` now reuse the EMP-010 SQL pushdown (predicates, COUNT,
ORDER BY, LIMIT/OFFSET in SQL) with parity tests pinning the old behavior.
The **live UAT build still materializes all jobs in Python** until the branch
merges and deploys. **Remove from live via:** merge + deploy of
`employed-uat-2026-06-10`.

## KL-11 — Deploys use floating `:uat` image tags

No SHA-pinned tags; rollback requires a rebuild instead of a tag flip
(CARTO-003). GHCR images also still live under `mekjr1/`, not the `xibodev` org
(CARTO-004). **Remove via:** BL-011, BL-012.

## KL-12 — Not registered with the xibodev-atlas control plane

No `atlas.json`, no CI `/register` step, no `xibodev.slug` label (Rule 8).
Deploy/reachability claims in the registry rely on direct HTTPS probes rather
than an Atlas record. **Remove via:** BL-013.

## KL-13 — Visual-verification gap from the 2026-06-10 run

37 of 55 screenshots (incl. `/terms`, `/privacy`, `/forgot-password`) have
automated pixel metrics but no direct multimodal scoring (model API image-cap
during the run). All serve HTTP 200 with no console errors. **Remove via:**
BL-010.
