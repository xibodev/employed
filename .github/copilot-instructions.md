# Copilot Instructions — employed.co.mz

## Project

FastAPI + Next.js job board with market selection by subdomain (`mx.*`, `mz.*`).
Frontend is in `frontend/`; backend is in `backend/`.

## Mandatory rules (from portfolio AI-OPS)

1. **No AI authorship trailers** — no `Co-Authored-By: Claude` lines, no
   "Generated with AI" footers in docs or commits.
2. **Never paste credentials** — reference file paths, not values.
3. **Locale codes** — `en`, `pt`, `es` only. Expand together across all products.
4. **Env var naming** — use standard names: `SENTRY_DSN`, `STRIPE_SECRET_KEY`,
   `STRIPE_WEBHOOK_SECRET`, `FROM_EMAIL`, `NEXT_PUBLIC_API_URL`,
   `NEXT_PUBLIC_APP_URL`, `FRONTEND_BASE_URL`. (Email goes through the Resend
   SMTP relay: `SMTP_PASSWORD` carries the Resend API key — there is no
   `RESEND_API_KEY` var in the app env.) Full map:
   `docs/architecture/CONFIG_AND_SECRETS_MAP.md`.
5. **Secrets posture** — never commit `.env`. See `deploy/.env.example` and `frontend/.env.example`.
6. **Port allocation** — frontend defaults to `localhost:3000`, backend to `localhost:8000`, MailHog to `8025` when used.

## Key files

- `CLAUDE.md` — current architecture notes
- `backend/app/main.py` — FastAPI app entrypoint
- `backend/app/config.py` — backend settings
- `backend/app/routers/` — API route modules
- `backend/app/models/` — SQLAlchemy models
- `frontend/src/lib/api.ts` — frontend API base URL handling
- `frontend/src/lib/market.ts` — hostname/subdomain market resolution
- `tests/README.md` — current testing guidance

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

> **Hard pre-deploy gate for branch `fix/quality-run-2026-06-10` (BL-001):**
> the `deploy-uat.yml` env upsert must first add `FRONTEND_BASE_URL`,
> `NEXT_PUBLIC_APP_URL`, `CORS_ORIGINS`, `ENVIRONMENT`, `SENTRY_DSN`,
> `SENTRY_ENVIRONMENT` — see `docs/architecture/DEPLOYMENT_TOPOLOGY.md`
> § "Deploy-time env gaps".

Concrete gaps (in priority order):

1. **Gate deploy on CI.** Today `deploy-uat.yml` triggers on every push to
   `uat`, racing `ci.yml`. Switch to `workflow_run` of `ci`
   (`types: [completed]` + `if: github.event.workflow_run.conclusion == 'success'`)
   OR add a `needs:` chain in a single workflow. A red CI must block the
   deploy job.
2. **Pin images by commit SHA.** Replace mutable `ghcr.io/mekjr1/employed-api:uat`
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
    Slack/Discord webhook (see `_integrations/` if one exists; otherwise add
    `DEPLOY_WEBHOOK_URL` to repo secrets).

Acceptance for "ready to clone into `deploy-prod.yml`":
- A failing `ci.yml` blocks any UAT deploy.
- The deployed image tag on Box 3 maps 1:1 to a git SHA you can `git show`.
- `alembic upgrade head` runs every deploy and is visible in workflow logs.
- A documented rollback flips Box 3 back to the previous SHA in under 2 minutes.
- Box 3 surfaces a single, accurate health signal per container.

When all 10 items are green on UAT, the prod workflow is essentially a copy
with: different secrets, different host, `environment: prod` protection, and
manual `workflow_dispatch` trigger.
