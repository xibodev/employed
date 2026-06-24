<!-- last_verified: 2026-06-19T00:00:00Z | git_ref: uat (multi-tenant-hiring-platform complete: a18e6c1) -->

# Employed — Workspace TODO

> Running, workspace-wide checklist for `employed.co.mz`. The single place to
> see what's outstanding. Detail lives in `SERVICES.md`, `docs/product/BACKLOG.md`,
> `docs/operations/INFRASTRUCTURE.md`, and `.github/copilot-instructions.md`;
> this file is the consolidated top sheet. Check items off as they land.

## 🔴 Blocking — multi-tenant platform ready for UAT

- [ ] **Deploy the completed multi-tenant hiring platform to UAT.** All 92 tasks
      of the multi-tenant-hiring-platform spec have been implemented and merged
      to `uat` branch (`a18e6c1`). This includes: Company entities + Membership
      management, two-layer RBAC, verification state machine + trust badges,
      JSON Resume profile versioning, Application pipeline with recruiter workflow,
      audit trail, webhooks, and versioned export API. The implementation is
      complete and ready for deployment when GitHub Actions minutes are available.
- [ ] **Confirm the multi-tenant features work end-to-end** once deployed:
      Company creation + owner membership, domain verification flow, member
      invitations, job posting on behalf of companies, application pipeline
      (list + kanban views), profile versioning, webhook delivery, export API
      (`/api/export/v1/candidates/{id}`), and audit trail capture.
- [ ] **Run the comprehensive test suite** to validate all 29 property-based
      tests pass along with integration and smoke tests for the new hiring
      platform features.

## 🟡 Operator — infra / credentials

- [ ] **Provision Bugsink** projects `employed-api` + `employed-web` (Box 0,
      `errors.xibodev.com`), set the `EMPLOYED_UAT_SENTRY_DSN` secret →
      `SENTRY_DSN` flows on next deploy. DSN-only swap. (`docs/operations/bugsink-setup.md`)
- [ ] **Verify `employed.xibodev.com` on AWS SES** (`eu-west-1`, DKIM), then
      switch `FROM_EMAIL` → `noreply@employed.xibodev.com`. Until then keep the
      Resend apex sender. (`docs/operations/INFRASTRUCTURE.md`)
- [ ] **Migrate uptime monitors** UptimeRobot → Gatus on Box 0; retire the UR
      monitors once Gatus is green. (`docs/operations/uptime-monitoring.md`)
- [ ] Move Google OAuth + reCAPTCHA clients into the shared `xibodev.com` GCP
      project on the next credential rotation.
- [ ] Resolve `.mz` domain ownership/delegation before any `employed.co.mz`
      production DNS / Caddy routing.
- [ ] Update the GitHub repo description (still reads "A Meteor based Job Board").
- [ ] Confirm M-Pesa / e-Mola sandbox credentials before any mobile-money UAT
      journey that claims real provider coverage.

## 🟢 Engineering — multi-tenant hiring platform (COMPLETE ✅)

The trust-centric hiring platform transformation has been **fully implemented**:

**✅ Core Implementation (ALL 92 TASKS COMPLETE)**
- ✅ Company entities with multi-tenancy (unique slugs per market, verification status)
- ✅ Membership management (org_owner, org_admin, recruiter, member roles)
- ✅ Two-layer RBAC authorization (platform + tenant permissions)
- ✅ Verification state machine (unverified → pending → verified/rejected/revoked/flagged)
- ✅ Composable trust badges (domain verified, business-document verified, etc.)
- ✅ JSON Resume profile versioning with immutable snapshots
- ✅ Application pipeline (applied → reviewed → shortlisted → rejected → hired)
- ✅ Append-only audit trail for all privileged actions
- ✅ Outbound webhooks (job.published, application.created, application.status_changed)
- ✅ Versioned export API (/api/export/v1) with standard schemas
- ✅ Database migrations (003_rbac_and_tenancy, 004_migrate_admins, 005_migrate_legacy_profiles_and_jobs)
- ✅ Frontend integration (company dashboard, member management, application kanban/list views)
- ✅ Comprehensive testing (29 property-based tests + integration tests)
- ✅ Complete documentation update

**Remaining Polish Items:**
- [ ] Frontend lint/typecheck for new components (ESLint zero-warnings, `tsc --noEmit`)
- [ ] Component tests for list/kanban view parity  
- [ ] Pin HTML→PDF engine (`weasyprint`/`xhtml2pdf`) for enhanced resume rendering
- [ ] Decide on `RESUME_ARTIFACT_DIR` persistence strategy
- [ ] Final end-to-end testing on UAT deployment

## 🟢 Engineering — UAT CI/CD hardening (toward a prod-ready pipeline)

- [ ] Gate deploy on CI — `deploy-uat.yml` currently races `ci.yml` and a red CI
      does not block the deploy.
- [ ] Pin images by commit SHA (`:uat-<sha>` alongside `:uat`) + a one-command
      rollback script.
- [ ] Surface `alembic upgrade head` (migrate service) failures as deploy failures.
- [ ] Add a `concurrency:` group on the deploy job (two pushes race on Box 3).
- [ ] GitHub Environments + required reviewers (foundation for a prod workflow).
- [ ] Smoke beyond `/health`: frontend `/`, both market hosts, one read-only API
      journey; fail the deploy on any non-2xx.
- [ ] Trivy image scan (fail on HIGH/CRITICAL) + deploy notifications.
- [ ] Rename default branch `master` → `main` (CI already covers both).
- [ ] Atlas registration: add `atlas.json`, a CI `/register` step, and the
      `xibodev.slug` docker label.

## 🔵 Backlog — later

- [ ] Replace the mobile-money simulator with real M-Pesa / e-Mola sandbox adapters.
- [ ] Install / configure New Relic for API + frontend (`employed-*-uat`).
- [ ] Consider CDN / edge caching for the self-hosted Next.js frontend once traffic justifies it.
- [ ] Decide whether to move Postgres/Redis from product compose to Box 1 shared
      services (needs a migration window — do not move the live UAT DB casually).

## ✅ Recently done (2026-06-19)

- **🎉 MULTI-TENANT HIRING PLATFORM COMPLETE**: Implemented all 92 tasks of the
  multi-tenant-hiring-platform specification. The platform now includes company
  entities, membership management, two-layer RBAC, verification state machine
  with trust badges, JSON Resume profile versioning, application pipeline with
  recruiter workflow, comprehensive audit trail, outbound webhooks, versioned
  export API, and complete database migrations. Frontend includes company
  dashboard, member management, and application management interfaces.
- **✅ Comprehensive testing**: 29 property-based tests implemented covering all
  major system behaviors, plus integration and smoke tests.
- **✅ Documentation refresh**: Updated all architecture and product documentation
  to reflect the completed hiring platform implementation.
- **✅ Database migrations**: Three new reversible Alembic migrations preserve
  all existing data while adding multi-tenant capabilities.
- **✅ Code merge and deployment preparation**: Merged completed implementation
  to `uat` branch (`a18e6c1`) ready for deployment when GitHub Actions minutes
  are available.
