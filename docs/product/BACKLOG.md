# Employed — Backlog

```yaml
last_verified: 2026-06-11T01:44:01Z
verified_by: backlog-feature-steward (quality run 2026-06-10_120309)
branch: fix/quality-run-2026-06-10 @ 7f4b5b8 (uat baseline 00aa899)
```

Actionable items only, each with an owner and the evidence that put it here.
Statuses use the registry's 8-status machine (`docs/product/FEATURE_REGISTRY.md`).
Long-standing environmental constraints live in `KNOWN_LIMITATIONS.md`; this file
tracks the work to remove them.

---

## P0 — prerequisites BEFORE merging/deploying `fix/quality-run-2026-06-10`

> **BL-001 is a hard pre-merge/pre-deploy gate.** Deploying the fix branch
> without it ships the new code with a deploy-env that never sets the variables
> the fixes depend on: email links fall back away from the frontend (re-breaking
> the EMP-004 funnel), credentialed cookie refresh fails against wildcard CORS
> (EMP-006), and robots/sitemap/market hosts lose their env-derived domains
> (EMP-013/024).

| ID | Item | Status | Owner | Source / evidence |
|---|---|---|---|---|
| BL-001 | **CARTO-002:** extend the `deploy-uat.yml` env upsert with `FRONTEND_BASE_URL`, `NEXT_PUBLIC_APP_URL`, `CORS_ORIGINS`, `ENVIRONMENT`, `SENTRY_DSN`, `SENTRY_ENVIRONMENT` (names only here; values from Actions secrets/vars per CREDENTIALS.md). Verified missing at `.github/workflows/deploy-uat.yml` upsert block on 2026-06-10. | `planned` | engineering | `architecture/repo-map.json` CARTO-002; workflow inspection this pass |
| BL-002 | Set `CORS_ORIGINS` to the **exact frontend origins** in every deployed env before cookie-auth (EMP-006) ships — credentialed CORS cannot use the wildcard default. Pairs with BL-001 (the upsert must carry it). | `planned` | operator | `fix-execution/execution-report.json` operator actions |

## P1 — unblock the in-flight release / open decisions

| ID | Item | Status | Owner | Source / evidence |
|---|---|---|---|---|
| BL-003 | **EMP-011:** provision Sentry projects `employed-api` + `employed-frontend` (org `nmtss`); set `SENTRY_DSN` + `SENTRY_ENVIRONMENT` in the deploy env; decide on `@sentry/nextjs` for the frontend; redeploy Box 3. Required before any prod traffic (release-decision pre-prod checklist). | `blocked` (external-ops) | operator | EMP-011; SERVICES.md observability table |
| BL-004 | **EMP-014:** verify the Stripe dashboard webhook endpoint URL ends with `/webhooks/_stripe/webhook` (the previously documented `/_stripe/webhook` 404s). In-repo smoke test already pins the route (`dee9a00`). | `blocked` (external-ops) | operator | EMP-014; execution report |
| BL-005 | **EMP-028 product decision:** should the poster's contact email remain visible to anonymous visitors on the public job detail page? It is how candidates apply today, but the public API already omits it (inconsistent policy). No safe unilateral default — needs the product owner's call, then a small fix either way. | `blocked` (product decision) | product/operator | EMP-028 (skipped by design); KL-06 |
| BL-006 | **CARTO-001:** extend the EMP-010 SQL pushdown to the public aliases the frontend actually calls — `/api/jobs` and `/api/featuredJobs` still materialize all jobs via `query_all` and filter in Python (`backend/app/routers/public_api.py:28`, `frontend/src/lib/api.ts:109-143`). | `planned` | engineering | `architecture/repo-map.json` CARTO-001 |
| BL-007 | **EMP-019 follow-up:** before M-Pesa/e-Mola go live, confirm with the providers that callbacks carry a `timestamp` field — the fix branch **rejects timestamp-less callbacks with 400** (deliberate contract change; providers are simulator/mock today). | `planned` | operator | execution report EMP-019 notes |

## P2 — quality, hardening, portfolio compliance

| ID | Item | Status | Owner | Source / evidence |
|---|---|---|---|---|
| BL-008 | **TD-004:** frontend component-test foundation — pick a runner (vitest/RTL), seed first tests for AuthContext/JobForm/admin panels. Backend coverage gaps already landed in their owning fixes. | `blocked` (tooling decision) | operator | TD-004 partial |
| BL-009 | **EMP-008 residual:** `_set_job_fields` reassigns `user_id`/`user_name` to the editor, so an admin edit silently transfers listing ownership. Out of scope in the EMP-008 commit; needs its own fix + test. | `planned` | engineering | execution report EMP-008 notes |
| BL-010 | Follow-up vision pass on `screenshot-analysis/_resized/` — 37 screenshots (incl. `/terms`, `/privacy`, `/forgot-password`) lack direct multimodal scoring; corpus is staged. | `planned` | engineering | REPORT.md §7 coverage deviation |
| BL-011 | **CARTO-003:** SHA-pinned image tags (`:uat-<sha>` alongside `:uat`) + rollback script — floating tags mean rollback requires a rebuild. Overlaps SERVICES.md "production CI/CD path" items 2/4. | `planned` | engineering | `architecture/repo-map.json` CARTO-003 |
| BL-012 | **CARTO-004:** move GHCR images `ghcr.io/mekjr1/employed-{api,frontend}` → `ghcr.io/xibodev/*` as part of the repo org migration (AI-OPS). Do the whole lift-and-shift in one turn. | `planned` | operator | `architecture/repo-map.json` CARTO-004 |
| BL-013 | **Atlas registration (Rule 8):** add `atlas.json`, a CI `/register` step, and the `xibodev.slug` docker label. Found absent this pass — `deployed_to_uat` rows currently rely on direct HTTPS probes instead of an Atlas record (finding BFS-005). | `planned` | engineering | ATLAS-ADOPTION.md; steward probe 2026-06-11T01:44:01Z |
| BL-014 | Consider shortening `REFRESH_TOKEN_EXPIRE_DAYS` from 7d now that the refresh token rides an httpOnly cookie (EMP-006 note). | `planned` | product/operator | execution report EMP-006 notes |
| BL-015 | **EMP-027 residuals:** API-origin error detail strings are English-only; admin UI not localized; job-type/currency/period option labels stay canonical API values. Locales: en/pt/es. | `planned` | engineering | execution report EMP-027 notes |
| BL-016 | Verify `employed.xibodev.com` in Resend, then switch `FROM_EMAIL` to `noreply@employed.xibodev.com` (currently apex `noreply@xibodev.com`). | `planned` | operator | SERVICES.md email section; KL-05 |
| BL-017 | Activate brand domain `employed.co.mz` (DNS NXDOMAIN today) — resolve ownership/delegation first; prod host plan (`api.`/`mx.`/`mz.employed.co.mz`) only after `.mz` DNS is approved. Pointing prod DNS is a 🟡 confirm-first action. | `blocked` (domain ownership) | operator | SERVICES.md; EMP-F-015 |
| BL-018 | Install/configure New Relic agents (`employed-api-uat`, `employed-frontend-uat`, optionally worker). | `planned` | operator | SERVICES.md observability; KL-02 |
| BL-019 | Replace mobile-money simulator mode with real M-Pesa/e-Mola sandbox integrations (`MPESA_WEBHOOK_SECRET` / `EMOLA_WEBHOOK_SECRET` absent today). Sequence after BL-007. | `planned` | operator | SERVICES.md payments; KL-04 |

---

## Disposition notes

- Nothing in this backlog is `in_progress` — the fix branch's work is complete
  and sits at `tested_locally` in the registry; no stale `in_progress` (>30 days)
  entries exist (first registry pass).
- Items BL-003/004/005/008/017 are `blocked` with named blockers and owners;
  everything else is `planned`.
