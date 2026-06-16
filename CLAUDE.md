<!-- last_verified: 2026-06-11T02:02:49Z | git_ref: fix/quality-run-2026-06-10 | verified_by: doc-drift audit, quality run 2026-06-10_120309 -->

# Employed - Architecture Notes

> Detailed observed-state maps live in `docs/architecture/` (API map, route
> map, data model, config & secrets map, deployment topology). Prefer those
> for anything load-bearing; this file is the short orientation.
>
> This repo is **self-contained** — it depends on no parent-folder docs.
> Infrastructure facts and portfolio conventions (deploy box, port block,
> domains, error/email/uptime standards, secrets boundary) are in
> `docs/operations/INFRASTRUCTURE.md`.

## Overview

Employed is a FastAPI + Next.js job board for localized markets. Market context is selected from the request hostname, primarily `mx.*` and `mz.*`.

## Technology Stack

- Backend: FastAPI
- Frontend: Next.js 15 / React 19 / TypeScript
- Data layer: SQLAlchemy + Alembic
- Testing: pytest, Playwright, frontend build + typecheck
- Payments: Stripe, M-Pesa, e-Mola

## Application Structure

```text
/backend         # FastAPI app, models, routers, workers, migrations, pytest suite
/frontend        # Next.js app router frontend
/deploy          # Compose files and deployment assets
/docs            # API, operations, product, ADRs
/tests           # Cross-project test docs and Playwright coverage
/public          # Static assets shared at repo level
```

## Current Product Scope

- Subdomain-localized public job listings
- `mx.*` and `mz.*` hostnames map to separate market contexts
- Job country is derived from the active market during creation
- Admin approval workflow: `pending` -> `active` -> `filled`/`inactive`
- 90-day listing expiration
- Featured job payments via Stripe, M-Pesa, and e-Mola
- reCAPTCHA protection for new job submissions
- Public API and health endpoints
- English / Spanish / Portuguese UI with per-market defaults (`mx → es`, `mz → pt`)

## Commands

```bash
npm run lint
cd backend && python -m pytest      # 134 tests as of fix/quality-run-2026-06-10
cd frontend && npm run build
cd frontend && npm run typecheck
npx playwright test tests/e2e/      # requires a running app stack
```

## Local Development Notes

- Frontend default URL: `http://localhost:3000`
- Backend default URL: `http://localhost:8000`
- Frontend API base URL is controlled by `NEXT_PUBLIC_API_URL`
- `mx.lvh.me` and `mz.lvh.me` remain useful for local market testing
- Deployment-oriented compose files live under `deploy/`

## Key Code Areas

- `backend/app/main.py` — FastAPI app entrypoint, middleware, router wiring
- `backend/app/config.py` — environment-driven settings
- `backend/app/routers/` — auth, jobs, payments, admin, profiles, reports, users
- `backend/app/models/` — SQLAlchemy models and enums
- `backend/app/workers/` — background task configuration
- `frontend/src/lib/api.ts` — frontend API client base URL handling
- `frontend/src/lib/market.ts` — hostname/subdomain market resolution
- `frontend/src/components/` — shared UI and page-level components

## Notes

- Historical Meteor-era documents are retired to `docs/archive/` (migration plan, redesign plan, package audit, ADRs `001`–`004`) — reference only; see `docs/archive/README.md`. Current ADRs `005`/`006` stay in `docs/decisions/`.
- All compose files live under `deploy/`; there are no root-level `docker-compose*.yml` files.
- The project was originally imported from `nate-strauser/wework`; the current codebase is now a separate FastAPI + Next.js implementation.

## Env var conventions

Standard env var names are used where applicable: `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_APP_URL` (deployment domain — never hardcode it in source), `FRONTEND_BASE_URL` (email link base). See `deploy/.env.example`, `frontend/.env.example`, and `docs/architecture/CONFIG_AND_SECRETS_MAP.md`.

Planned provider cutovers (DSN/credential swaps, no code change): `SENTRY_DSN` will point at **Bugsink** on Box 0 (`errors.xibodev.com`); email moves from Resend to **AWS SES** (`eu-west-1`). Details in `docs/operations/INFRASTRUCTURE.md`.

## AI Assistant Rules

- No `Co-Authored-By: Claude` trailers, no AI authorship attribution in docs or commits.
- Never paste credentials into chat or commit them. Reference secrets by name; values live in GitHub Actions secrets or the operator vault (`docs/operations/INFRASTRUCTURE.md` § Secrets boundary).
- Locale codes: `en`, `pt`, `es` only — no extended tags like `pt-MZ`.
