<!-- last_verified: 2026-06-11T02:02:49Z | git_ref: fix/quality-run-2026-06-10 | verified_by: doc-drift audit, quality run 2026-06-10_120309 -->

# Employed

Employed is a multilingual job board for Mozambique and Mexico, localized by subdomain and rebuilt on a FastAPI + Next.js stack.

Companies can post roles, candidates can browse active opportunities, and admins can moderate listings before they go live.

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
| [`docs/architecture/`](docs/architecture/) | Observed-state architecture bundle (API map, routes, data model, config map, deployment topology) |
| [`docs/product/`](docs/product/) | Feature registry, backlog, known limitations, release notes |
| [`docs/api-reference.md`](docs/api-reference.md) | API documentation |
| [`docs/payment-flows.md`](docs/payment-flows.md) | Stripe, M-Pesa, and e-Mola flows |
| [`docs/markets-and-locales.md`](docs/markets-and-locales.md) | Market and locale behaviour |
| [`docs/operations-runbook.md`](docs/operations-runbook.md) | Incident response and operational procedures |
| [`docs/settings-reference.md`](docs/settings-reference.md) | Environment variable reference |
| [`docs/decisions/`](docs/decisions/) | Architecture Decision Records (001–004 are superseded Meteor-era decisions) |
| [`MIGRATION-PLAN.md`](MIGRATION-PLAN.md) | Historical Meteor → FastAPI/Next.js migration plan |
| [`brand/`](brand/) | Brand kit assets |

## Testing

```bash
npm run lint
cd backend && python -m pytest
cd frontend && npm run build && npm run typecheck
npx playwright test tests/e2e/
```

## History

This project started as a fork of `nate-strauser/wework` and has since been migrated away from Meteor. Historical migration documents are kept in the repo where they still provide context.