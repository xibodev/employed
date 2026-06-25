# Employed — Backlog

```yaml
last_verified: 2026-06-11T04:50:00Z
verified_by: fix-executor follow-up pass (quality run 2026-06-10_120309)
branch: fix/quality-run-2026-06-10 (uat baseline 00aa899)
```

Actionable items only, each with an owner and the evidence that put it here.
Statuses use the registry's 8-status machine (`docs/product/FEATURE_REGISTRY.md`).
Long-standing environmental constraints live in `KNOWN_LIMITATIONS.md`; this file
tracks the work to remove them.

---

## P0 — prerequisites BEFORE merging/deploying `fix/quality-run-2026-06-10`

> **BL-001 gate: resolved on branch, pending merge (2026-06-11).** The
> `deploy-uat.yml` env upsert now sets every variable the fixes depend on
> (`FRONTEND_BASE_URL`, `NEXT_PUBLIC_APP_URL`, exact-origin `CORS_ORIGINS`,
> `ENVIRONMENT=uat`, `SENTRY_DSN`, `SENTRY_ENVIRONMENT=uat`). The gate fully
> clears when the branch merges to `uat` and a green deploy run applies the
> upsert on Box 3.

| ID | Item | Status | Owner | Source / evidence |
|---|---|---|---|---|
| BL-001 | **CARTO-002:** extend the `deploy-uat.yml` env upsert with `FRONTEND_BASE_URL`, `NEXT_PUBLIC_APP_URL`, `CORS_ORIGINS`, `ENVIRONMENT`, `SENTRY_DSN`, `SENTRY_ENVIRONMENT`. **Resolved on branch 2026-06-11** — upsert block extended (validated: YAML parse + `bash -n` on the deploy script); `SENTRY_DSN` reads the optional `EMPLOYED_UAT_SENTRY_DSN` secret (empty-safe). Pending merge + deploy to take effect on Box 3. | `tested_locally` | engineering | `architecture/repo-map.json` CARTO-002; `.github/workflows/deploy-uat.yml` upsert block this commit |
| BL-002 | Set `CORS_ORIGINS` to the **exact frontend origins** in every deployed env before cookie-auth (EMP-006) ships. **UAT covered by BL-001** (workflow upserts the three `*.employed.xibodev.com` origins); remains an operator checklist item for any future env (prod) whose origins differ. | `planned` (UAT covered) | operator | `fix-execution/execution-report.json` operator actions; BL-001 upsert |

## P1 — hiring-platform evolution (multi-tenant-hiring-platform spec)

The trust-centric, integration-ready hiring platform (multi-tenancy, two-layer
RBAC, verification + trust badges, version-controlled profiles, applications
pipeline, audit trail, webhooks, versioned export API) is implemented across the
backend (migrations `003`–`005`; new models/services/routers) and the frontend
tenant/hiring surfaces. Remaining work to close the spec:

| ID | Item | Status | Owner | Source / evidence |
|---|---|---|---|---|
| MTH-001 | Frontend lint/typecheck + component tests for the new tenant/hiring segments (company dashboard, members, verification status, applications list+kanban); ESLint zero-warnings, `tsc --noEmit`, list/kanban parity test | `in_progress` | engineering | tasks.md 18.5 |
| MTH-002 | Confirm **arq (not Celery)** for server-side PDF resume rendering (DD-7 deviation flagged in design — R14.2 names Celery; the codebase has no Celery). Behavior is implemented on arq; needs product/operator sign-off | `planned` | engineering | design.md DD-7 |
| MTH-003 | Pin an HTML→PDF engine (`weasyprint`/`xhtml2pdf`) in `requirements-api.txt` for richer resume PDFs; today `resume_templates._html_to_pdf` uses an engine if installed and otherwise a self-contained text-PDF fallback | `planned` | engineering | `backend/app/services/resume_templates.py` module docstring |
| MTH-004 | Optionally make `RESUME_ARTIFACT_DIR` an explicit, persisted volume in deploy compose (defaults to a system temp subdir today) | `planned` | operator | `docs/architecture/CONFIG_AND_SECRETS_MAP.md` |
| MTH-005 | Cross-market companies (Open Decision 2 deferred): a `Company` is single-market today. Revisit if a tenant needs to span `mz`/`mx` | `planned` | product | design.md Open Decision 2 |

## P1 — unblock the in-flight release / open decisions

| ID | Item | Status | Owner | Source / evidence |
|---|---|---|---|---|
| BL-003 | **EMP-011:** provision Sentry projects `employed-api` + `employed-frontend` (org `nmtss`); set `SENTRY_DSN` + `SENTRY_ENVIRONMENT` in the deploy env; decide on `@sentry/nextjs` for the frontend; redeploy Box 3. Required before any prod traffic (release-decision pre-prod checklist). | `blocked` (external-ops) | operator | EMP-011; SERVICES.md observability table |
| BL-004 | **EMP-014:** verify the Stripe dashboard webhook endpoint URL ends with `/webhooks/_stripe/webhook` (the previously documented `/_stripe/webhook` 404s). In-repo smoke test already pins the route (`dee9a00`). | `blocked` (external-ops) | operator | EMP-014; execution report |
| BL-005 | **EMP-028 product decision:** poster contact-email exposure. **Decided + implemented 2026-06-11** (operator authorized acting on the open decision): contact is auth-gated everywhere — anonymous payloads return `null`, signed-in users get an explicit reveal, anonymous visitors get a sign-in CTA; URL/WhatsApp apply paths stay public. Policy + reversal path documented in KL-06. | `tested_locally` | engineering | EMP-028 regression tests in `tests/test_jobs.py`; KL-06 policy entry |
| BL-006 | **CARTO-001:** extend the EMP-010 SQL pushdown to the public aliases the frontend actually calls (`/api/jobs`, `/api/featuredJobs`). **Resolved on branch 2026-06-11** — both aliases now reuse the shared `_job_query_pushdown` helpers (SQL predicates/COUNT/ORDER BY/LIMIT-OFFSET); parity + SQL-shape regression tests added in `tests/test_public_api.py`; `/api/featuredJobs` keeps its deterministic newest-first contract. | `tested_locally` | engineering | `architecture/repo-map.json` CARTO-001; `backend/app/routers/public_api.py` + `tests/test_public_api.py` this commit |
| BL-007 | **EMP-019 follow-up:** before M-Pesa/e-Mola go live, confirm with the providers that callbacks carry a `timestamp` field — the fix branch **rejects timestamp-less callbacks with 400** (deliberate contract change; providers are simulator/mock today). | `planned` | operator | execution report EMP-019 notes |

## P2 — quality, hardening, portfolio compliance

| ID | Item | Status | Owner | Source / evidence |
|---|---|---|---|---|
| BL-008 | **TD-004:** frontend component-test foundation — pick a runner (vitest/RTL), seed first tests for AuthContext/JobForm/admin panels. Backend coverage gaps already landed in their owning fixes. **Attempted + skipped 2026-06-11 (fix-executor):** `npm install -D vitest jsdom @vitejs/plugin-react @testing-library/react @testing-library/dom` ERESOLVEs on a pre-existing project conflict — `next@15.0.0` peer-accepts only `react@^18.2.0 \|\| 19.0.0-rc-65a56d0e-20241020` while the project pins stable `react@19.0.0`, so ANY new dependency install fails. Unblock first by either (a) bumping Next to >=15.1 (peer range includes stable React 19) or (b) committing to `legacy-peer-deps=true` in `frontend/.npmrc` — both are operator-level toolchain decisions, out of scope for a test-infra item. No files were changed by the attempt. | `blocked` (Next/React peer-dep decision) | operator | TD-004 partial; npm ERESOLVE log 2026-06-11 |
| BL-009 | **EMP-008 residual:** `_set_job_fields` reassigns `user_id`/`user_name` to the editor, so an admin edit silently transfers listing ownership. Out of scope in the EMP-008 commit; needs its own fix + test. | `planned` | engineering | execution report EMP-008 notes |
| BL-010 | Follow-up vision pass on `screenshot-analysis/_resized/` — 37 screenshots (incl. `/terms`, `/privacy`, `/forgot-password`) lack direct multimodal scoring; corpus is staged. | `planned` | engineering | REPORT.md §7 coverage deviation |
| BL-011 | **CARTO-003:** SHA-pinned image tags (`:uat-<sha>` alongside `:uat`) + rollback script — floating tags mean rollback requires a rebuild. Overlaps SERVICES.md "production CI/CD path" items 2/4. | `planned` | engineering | `architecture/repo-map.json` CARTO-003 |
| BL-012 | **CARTO-004:** move GHCR images `ghcr.io/mekjr1/employed-{api,frontend}` → `ghcr.io/xibodev/*` as part of the repo org migration. | `done` (2026-06-25 — repo transferred to `xibodev/employed`; images now `ghcr.io/xibodev/employed-{api,frontend}`, Box 3 authenticates to pull private org packages) | operator | `architecture/repo-map.json` CARTO-004 |
| BL-013 | **Atlas registration:** add `atlas.json`, a CI `/register` step, and the `xibodev.slug` docker label. Found absent this pass — `deployed_to_uat` rows currently rely on direct HTTPS probes instead of an Atlas record (finding BFS-005). | `planned` | engineering | steward probe 2026-06-11T01:44:01Z |
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
- Items BL-003/004/008/017 are `blocked` with named blockers and owners;
  BL-001/005/006 moved to `tested_locally` on 2026-06-11 (fix-executor
  follow-up pass); everything else is `planned`.
