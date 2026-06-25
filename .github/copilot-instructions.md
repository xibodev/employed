# Copilot Instructions — Employed

## Project

**Trust-centric, integration-ready hiring platform** for Mozambique (MZ) and Mexico (MX) built on FastAPI + Next.js 15. **Multi-tenant hiring platform implementation complete** with company management, two-layer RBAC, verification & trust system, application pipeline, and integration APIs. Frontend is in `frontend/`; backend is in `backend/`.

**🎉 ALL 92 TASKS COMPLETE**: Company entities + membership management, two-layer RBAC authorization, verification state machine + trust badges, JSON Resume profile versioning, Application pipeline with recruiter workflow, append-only audit trail, outbound webhooks, versioned export API, database migrations (003-005), and comprehensive frontend integration.

## Mandatory rules (self-contained)

1. **No AI authorship trailers** — no `Co-Authored-By: Claude` lines, no
   "Generated with AI" footers in docs or commits.
2. **Never paste credentials** — reference file paths, not values.
3. **Locale codes** — `en`, `pt`, `es` only. Expand together across all products.
4. **Env var naming** — use standard names: `SENTRY_DSN`, `STRIPE_SECRET_KEY`,
   `STRIPE_WEBHOOK_SECRET`, `FROM_EMAIL`, `NEXT_PUBLIC_API_URL`,
   `NEXT_PUBLIC_APP_URL`, `FRONTEND_BASE_URL`. (Email goes through the Resend
   SMTP relay: `SMTP_PASSWORD` carries the Resend API key — there is no
   `RESEND_API_KEY` var in the app env.) Full map:
   `docs/architecture/CONFIG_AND_SECRETS_MAP.md`. The hiring platform adds one
   optional var, `RESUME_ARTIFACT_DIR` (PDF artifact output dir); the webhook
   backoff knobs are module constants, not env vars.
5. **Secrets posture** — never commit `.env`. See `deploy/.env.example` and `frontend/.env.example`.
6. **Port allocation** — frontend defaults to `localhost:3000`, backend to `localhost:8000`, MailHog to `8025` when used.

## Key files

- `CLAUDE.md` — current architecture notes
- `backend/app/main.py` — FastAPI app entrypoint (includes new hiring platform routers)
- `backend/app/config.py` — backend settings
- `backend/app/routers/` — API route modules (includes companies, memberships, applications, verification, export_api, webhooks_admin)
- `backend/app/services/` — Business logic (rbac, verification, trust, companies, memberships, applications, webhooks, export)
- `backend/app/models/` — SQLAlchemy models (includes company, membership, application, audit_log, profile_version, webhook)
- `backend/alembic/versions/` — Database migrations (003_rbac_and_tenancy, 004_migrate_admins, 005_migrate_legacy_profiles_and_jobs)
- `frontend/src/components/company/` — Company management UI components
- `frontend/src/components/applications/` — Application pipeline UI (list + kanban views)
- `frontend/src/contexts/TenantContext.tsx` — Tenant (company) context management
- `docs/architecture/` — Comprehensive architecture documentation including RBAC_AND_TENANCY.md, VERIFICATION_AND_TRUST.md, INTEGRATION_AND_EXPORT.md

## Multi-Tenant Hiring Platform Architecture

**Authorization Model**
- **Two layers**: Platform permissions (cross-tenant) + tenant permissions (company-scoped)
- **Authorization primitive**: Atomic permissions (`job:post`, `company:verify`) not role names
- **Tenant scope**: Resolved from target resource's `company_id`
- **require_permission()** FastAPI dependency for all authorization checks

**Core Entities**
- **Company**: Multi-tenant organization with verification_status, trust_badges, verified_email_domains
- **Membership**: User↔Company relationship with role (org_owner, org_admin, recruiter, member) and status
- **Application**: First-class pipeline entity (applied → reviewed → shortlisted → rejected → hired)
- **ProfileVersion**: Immutable JSON Resume snapshots of live profiles
- **AuditLog**: Append-only trail for all privileged actions

**Trust & Verification**
- **State machine**: unverified → pending → verified/rejected/revoked/flagged (reusable across entities)
- **Trust badges**: Composable named signals (domain verified, business-document verified, etc.)
- **Domain verification**: DNS TXT records or matching member email addresses

**Integration & Export** 
- **Webhooks**: job.published, application.created, application.status_changed with retry logic
- **Export API**: /api/export/v1/ returning JSON Resume (candidates), JobPosting JSON-LD (jobs)
- **External refs**: JSONB fields on all major entities for ATS integration without migrations
- `backend/app/services/` — business logic (RBAC, verification, trust, companies, memberships, applications, webhooks, export)
- `backend/app/models/` — SQLAlchemy models
- `frontend/src/lib/api.ts` — frontend API base URL handling
- `frontend/src/lib/market.ts` — hostname/subdomain market resolution
- `frontend/src/lib/tenant.ts` — active company (tenant) context, kept separate from market
- `tests/README.md` — current testing guidance

## Hiring-platform conventions (multi-tenant-hiring-platform spec)

The job board is evolving into a trust-centric, integration-ready hiring
platform. New work follows these conventions:

1. **Layering.** New API routes go in `routers/` (one module per domain) and are
   wired in `main.py`; business logic lives in `services/`; validation in
   `schemas/`. Models extend `Base` in `models/`; enums use the `pg_enum` helper
   in `models/enums.py`.
2. **Authorization is permission-based (two-layer RBAC).** Check for a
   *permission* string (e.g. `job:moderate`), never a role name, via
   `services/rbac.py#require_permission`. Effective permissions = platform-role
   permissions (across all tenants) ∪ the **active** membership's tenant-role
   permissions in the resource's company. `invited`/`suspended` memberships grant
   none. See `docs/architecture/RBAC_AND_TENANCY.md`.
3. **Market vs tenant are orthogonal.** Market is resolved from the hostname;
   tenant (Company) is resolved from the target resource + the user's membership.
   Never derive one from the other.
4. **Verification is one shared state machine.** Route all verification
   transitions through `services/verification.py#transition` (it validates,
   reconciles trust badges, and writes one audit row atomically). Trust is a set
   of named badges, not a numeric score.
5. **Audit + profile versions are append-only.** Write privileged/verification/
   moderation actions via `services/audit.py`; never add an update/delete path —
   `AuditLog` and `ProfileVersion` have `before_update` guards that raise.
6. **Background work uses arq, not Celery.** PDF resume rendering and webhook
   delivery are arq tasks in `app/workers/tasks.py`. Webhook delivery retries use
   bounded exponential backoff via **module constants** (not env vars).
7. **Standard schemas at boundaries.** Use the pure mappers in `services/export.py`
   (JSON Resume, schema.org `JobPosting` JSON-LD, normalized Application). Every
   major entity has an `external_refs` JSONB field — map external ids there, never
   via a migration. The export API is versioned in the path (`/export/v1`).
8. **Migrations are append-only.** The tenancy/RBAC schema is migration `003`;
   data migrations are `004` (legacy admins → `platform_super_admin`) and `005`
   (legacy company profiles → companies, `status_history` → audit). Add new
   revisions; never edit `001`–`005`. See `docs/architecture/MIGRATION_STRATEGY.md`.

## Commands

```bash
npm run lint
cd backend && python -m pytest
cd frontend && npm run build
cd frontend && npm run typecheck
npx playwright test tests/e2e/
```

## Current workstream — harden UAT CI/CD into a prod-ready pipeline

UAT is live on Box 3 and stable, so the next priority is hardening
`.github/workflows/deploy-uat.yml` so it can be safely promoted into a
`deploy-prod.yml` later. **Do NOT introduce a prod workflow yet** — first close
the gaps below on UAT. Each item should ship as its own PR with a green CI
run before merge.

> **Pre-deploy gate BL-001 for branch `fix/quality-run-2026-06-10`:
> resolved on branch, pending merge (2026-06-11).** The `deploy-uat.yml` env
> upsert now adds `FRONTEND_BASE_URL`, `NEXT_PUBLIC_APP_URL`, `CORS_ORIGINS`,
> `ENVIRONMENT`, `SENTRY_DSN`, `SENTRY_ENVIRONMENT` — see
> `docs/architecture/DEPLOYMENT_TOPOLOGY.md` § "Deploy-time env gaps".

Concrete gaps (in priority order):

1. **Gate deploy on CI.** Today `deploy-uat.yml` triggers on every push to
   `uat`, racing `ci.yml`. Switch to `workflow_run` of `ci`
   (`types: [completed]` + `if: github.event.workflow_run.conclusion == 'success'`)
   OR add a `needs:` chain in a single workflow. A red CI must block the
   deploy job.
2. **Pin images by commit SHA.** Replace mutable `ghcr.io/xibodev/employed-api:uat`
   tags with `:uat-${{ github.sha }}` (push *both* `:uat` and the SHA tag so
   the floating tag still works for humans). The deploy step then sets
   `IMAGE_TAG` in `.env` and `docker compose pull` + `up -d` uses the SHA.
   This is the foundation for rollback and for promoting an exact UAT image
   into prod.
3. **Surface migration failures in the deploy.** Migrations DO run — the
   compose `migrate` service executes `alembic upgrade head` before
   backend/worker start — but the workflow doesn't surface a migration
   failure as a deploy failure. Add an explicit
   `docker compose run --rm migrate` step (or check the service exit code)
   after `pull` and before `up -d`, and fail the deploy if it errors.
4. **One-command rollback.** Add `scripts/rollback-uat.sh` that takes a prior
   SHA, edits `/opt/employed/.env`'s `IMAGE_TAG`, pulls, and restarts. Once
   step 2 ships, this becomes trivial.
5. **`concurrency:` group on deploy.** Two pushes in quick succession
   currently race each other on Box 3. Add
   `concurrency: { group: deploy-uat, cancel-in-progress: false }`.
6. **GitHub Environments + required reviewers.** Move UAT secrets behind an
   `environment: uat` block, then create an `environment: prod` with required
   reviewers — this is the protection prod will need on day one.
7. **Smoke beyond `/health`.** Today only backend `/health` is polled.
   Extend to: frontend `/`, both market hosts (`mx.employed.xibodev.com`,
   `mz.employed.xibodev.com`), and at least one read-only API journey
   (e.g. `GET /jobs?limit=1`). Fail the deploy on any non-2xx.
8. **Worker healthcheck override — DONE in repo, pending deploy.** A
   Redis-ping healthcheck for the worker is committed in
   `deploy/docker-compose.prod.yml`; the live box keeps showing the
   false-negative "unhealthy" until the next deploy ships it.
9. **Image vulnerability scan.** Add a Trivy scan step on the built image
   *before* push; fail on HIGH/CRITICAL. Acceptable allow-list lives in
   `.trivyignore`.
10. **Deploy notifications.** Post success/failure + commit SHA + actor to a
    Slack/Discord webhook via a `DEPLOY_WEBHOOK_URL` repo secret.

Acceptance for "ready to clone into `deploy-prod.yml`":
- A failing `ci.yml` blocks any UAT deploy.
- The deployed image tag on Box 3 maps 1:1 to a git SHA you can `git show`.
- `alembic upgrade head` runs every deploy and is visible in workflow logs.
- A documented rollback flips Box 3 back to the previous SHA in under 2 minutes.
- Box 3 surfaces a single, accurate health signal per container.

When all 10 items are green on UAT, the prod workflow is essentially a copy
with: different secrets, different host, `environment: prod` protection, and
manual `workflow_dispatch` trigger.
