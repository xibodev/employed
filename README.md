<!-- last_verified: 2026-06-15T00:00:00Z | git_ref: fix/quality-run-2026-06-10 | verified_by: self-contained cleanse 2026-06-15 -->

# Employed

Employed is a multilingual hiring platform for Mozambique and Mexico, localized by subdomain and built on a FastAPI + Next.js stack.

It began as a job board — companies post roles, candidates browse active opportunities, and admins moderate listings before they go live — and is evolving into a trust-centric, integration-ready hiring platform: *more than a job board, less than a heavy ATS*. That evolution adds multi-tenant companies and memberships, a two-layer permission-based access model, per-entity verification with composable trust badges, version-controlled JSON Resume profiles, a lightweight applications pipeline, an append-only audit trail, outbound webhooks, and a versioned export API exposing standard schemas (JSON Resume, schema.org `JobPosting`). Market (geography/locale/payment) and tenant (organization) remain orthogonal axes.

## Markets

The active market is resolved from the first hostname label:

- `mx.*` serves the MX market
- `mz.*` serves the MZ market

For local browser testing, `mx.lvh.me` and `mz.lvh.me` are still useful because `lvh.me` resolves to `127.0.0.1` without hosts-file changes.

## Languages

The product supports English, Spanish, and Portuguese. Each market has a default locale (MX → `es`, MZ → `pt`), while visitors can override language in the frontend.

## Technology stack

- **Backend:** FastAPI, SQLAlchemy, Alembic, pytest
- **Frontend:** Next.js 15, React 19, TypeScript
- **Payments:** Stripe, M-Pesa, e-Mola
- **Testing:** backend pytest, frontend build/typecheck, Playwright E2E

## Repository layout

```text
/backend    FastAPI API, models, routers, workers, migrations, pytest suite
/frontend   Next.js app router frontend
/deploy     Container and environment-specific compose files
/docs       Product, API, operations, and ADR documentation
/tests      Cross-project test docs and Playwright E2E coverage
```

## Development notes

- Frontend defaults to `http://localhost:3000`
- Frontend talks to the API via `NEXT_PUBLIC_API_URL`, which defaults to `http://localhost:8000`
- All compose files live under `deploy/` (`docker-compose.yml` + `dev`/`test`/`prod` overlays); there are no root-level compose files
- The deployment domain is never hardcoded: the frontend derives hosts from `NEXT_PUBLIC_APP_URL`, the backend builds email links from `FRONTEND_BASE_URL` (current UAT value: the `employed.xibodev.com` hosts)

## Documentation

| Document | Description |
| --- | --- |
| [`CLAUDE.md`](CLAUDE.md) | Current architecture notes for FastAPI + Next.js |
| [`DEPLOY.md`](DEPLOY.md) | Deployment topology and procedures (Box 3 UAT) |
| [`docs/operations/INFRASTRUCTURE.md`](docs/operations/INFRASTRUCTURE.md) | Self-contained infra context: box, port block, domains, error/email/uptime standards, secrets boundary |
| [`docs/architecture/`](docs/architecture/) | Observed-state architecture bundle (API map, routes, data model, config map, deployment topology, plus RBAC & tenancy, verification & trust, integration & export, and migration strategy) |
| [`docs/product/`](docs/product/) | Positioning, user types & journeys, feature registry, backlog, known limitations, release notes |
| [`docs/api-reference.md`](docs/api-reference.md) | API documentation |
| [`docs/payment-flows.md`](docs/payment-flows.md) | Stripe, M-Pesa, and e-Mola flows |
| [`docs/markets-and-locales.md`](docs/markets-and-locales.md) | Market and locale behaviour |
| [`docs/operations-runbook.md`](docs/operations-runbook.md) | Incident response and operational procedures |
| [`docs/settings-reference.md`](docs/settings-reference.md) | Environment variable reference |
| [`docs/decisions/`](docs/decisions/) | Architecture Decision Records (current: `005`, `006`) |
| [`docs/archive/`](docs/archive/) | Retired Meteor-era docs (migration plan, redesign, ADRs 001–004) — reference only |
| [`brand/`](brand/) | Brand kit assets |

## Testing

```bash
npm run lint
cd backend && python -m pytest
cd frontend && npm run build && npm run typecheck
npx playwright test tests/e2e/
```

## History

This project started as a fork of `nate-strauser/wework` and has since been migrated away from Meteor. Historical migration documents are retired to [`docs/archive/`](docs/archive/) for reference.