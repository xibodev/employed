<!-- last_verified: 2026-06-15T00:00:00Z | git_ref: fix/quality-run-2026-06-10 → uat (e168f8b) -->

# Employed — Workspace TODO

> Running, workspace-wide checklist for `employed.co.mz`. The single place to
> see what's outstanding. Detail lives in `SERVICES.md`, `docs/product/BACKLOG.md`,
> `docs/operations/INFRASTRUCTURE.md`, and `.github/copilot-instructions.md`;
> this file is the consolidated top sheet. Check items off as they land.

## 🔴 Blocking — release is built but not live

- [ ] **Re-auth Box 3 to GHCR and redeploy.** Deploy run `27585388941`
      (2026-06-15) failed: `docker compose pull` on Box 3 returned
      `ghcr.io/mekjr1/employed-api:uat … error from registry: denied`. Images
      built + pushed fine; the box just can't pull them (expired token or
      package perms). Fix on Box 3: `docker login ghcr.io -u <user> --password-stdin`
      with a valid PAT (or make the `employed-api`/`employed-frontend` GHCR
      packages readable), then re-run the **Deploy UAT** workflow.
- [ ] **Confirm the release actually went live** once the deploy succeeds:
      `api.employed.xibodev.com/health` → 200 (db+redis ok); worker healthcheck
      green (no more false-negative); and the EMP fixes are live — admin reports
      no longer 500, anonymous job posting works, verify/reset email links open
      (no 405), and `mx.*` serves MX data (X-Forwarded-Host).
- [ ] **CI is red on the release (`e168f8b`)** — pre-existing on the branch, not
      gated on deploy. Fix before promoting toward prod:
      - `backend-test`: 8 failures in `backend/tests/test_public_api.py` — the
        Redis rate-limiter returns `429` to the test client (test isolation:
        reset/disable the limiter per-test or flush Redis between tests) plus a
        `KeyError: 'items'` in the query-filter parity test.
      - `backend-lint`: `ruff format backend/tests/test_auth.py` (1 file).

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

## 🟢 Engineering — hiring-platform evolution (multi-tenant-hiring-platform spec)

The trust-centric hiring platform (multi-tenant companies/memberships, two-layer
RBAC, verification + trust badges, version-controlled profiles, applications
pipeline, audit trail, webhooks, versioned `/export/v1` API; migrations
`003`–`005`) is implemented backend + frontend. Outstanding:

- [ ] Frontend lint/typecheck + component tests for the new tenant/hiring
      segments (company dashboard, members, verification status, applications
      list+kanban) — ESLint zero-warnings, `tsc --noEmit`, list/kanban parity
      (tasks.md 18.5). → BACKLOG MTH-001
- [ ] Sign off the **arq-not-Celery** decision for PDF resume rendering (DD-7
      deviation: R14.2 names Celery; the stack has no Celery). → MTH-002
- [ ] Pin an HTML→PDF engine (`weasyprint`/`xhtml2pdf`) in `requirements-api.txt`
      for richer resume PDFs (text-PDF fallback today). → MTH-003
- [ ] Decide whether `RESUME_ARTIFACT_DIR` needs a persisted deploy volume
      (defaults to a system temp subdir). → MTH-004
- [ ] Final spec checkpoint: ensure the full backend + frontend test suites pass
      (tasks.md 20).

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

## ✅ Recently done (2026-06-15)

- Self-contained cleanse: severed all `_integrations/*` dependencies; added
  `docs/operations/INFRASTRUCTURE.md` as the in-repo home for portfolio facts.
- Retired Meteor-era docs to `docs/archive/`; replaced Sentry/UptimeRobot
  runbooks with Bugsink/Gatus; scrubbed the hardcoded Box 3 IP.
- Merged `fix/quality-run-2026-06-10` → `uat` (`e168f8b`) and pushed (deploy
  failed at the GHCR pull — see 🔴 above).
