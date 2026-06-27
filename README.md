<!-- last_verified: 2026-06-27T00:00:00Z| git_ref: master| verified_by: prod documentation refresh -->

# Employed

Employed is a trust-centric, integration-ready hiring platform for Mozambique and Mexico: more than a job board, less than a heavy ATS.

Production runs at `joinemployed.com`. The apex and `mz.joinemployed.com` serve the MZ market, `mx.joinemployed.com` serves the MX market, `www.joinemployed.com` is the canonical www host, and `api.joinemployed.com` serves the FastAPI API through Cloudflare Tunnel.

## Core features

- Multi-tenant companies and memberships.
- Two-layer permission-based RBAC: platform permissions plus company-scoped tenant permissions.
- Shared verification state machine and composable trust badges.
- JSON Resume profile versioning.
- First-class application pipeline with recruiter workflow.
- Append-only audit trail.
- Outbound webhooks and versioned `/export/v1` API.
- Market-localized jobs, pricing, providers, and locales.

## Markets and languages

The active market is resolved from the first hostname label:

- `mx.*` serves the MX market with default locale `es`.
- `mz.*` and the apex serve the MZ market with default locale `pt`.
- `en`, `pt`, and `es` are the supported locale codes.

## Technology stack

- Backend: FastAPI, SQLAlchemy, Alembic, arq, Redis.
- Frontend: Next.js 15.5.19, React 19, TypeScript.
- Production runtime: Vercel frontend; AWS EC2 Docker Compose backend; RDS PostgreSQL 17; Cloudflare DNS/Tunnel.
- Payments: Stripe test mode; M-Pesa/e-Mola simulator mode.
- Email: AWS SES for `joinemployed.com`.

## Repository layout

```text
/backend         FastAPI API, models, routers, workers, migrations, pytest suite
/frontend        Next.js app router frontend
/deploy/ec2      Production EC2 bootstrap, compose, env render, secret list
/infrastructure  Python CDK production infrastructure
/docs            Product, API, architecture, operations, and ADR documentation
/tests           Playwright E2E coverage
```

## Development notes

- Frontend defaults to `http://localhost:3000`.
- API defaults to `http://localhost:8000`.
- Frontend API base URL is `NEXT_PUBLIC_API_URL`.
- Deployment domain is config-driven through `NEXT_PUBLIC_APP_URL` and `FRONTEND_BASE_URL`.
- Local market testing can use `mx.lvh.me` and `mz.lvh.me`.

## Documentation

| Document | Description |
| --- | --- |
| [`CLAUDE.md`](CLAUDE.md) | Short current architecture orientation |
| [`DEPLOY.md`](DEPLOY.md) | Production deployment procedure |
| [`SERVICES.md`](SERVICES.md) | Canonical live service state |
| [`docs/operations/INFRASTRUCTURE.md`](docs/operations/INFRASTRUCTURE.md) | Infrastructure and operating context |
| [`docs/architecture/`](docs/architecture/) | Architecture, routes, data, dependencies, deployment topology |
| [`docs/product/`](docs/product/) | Positioning, feature registry, backlog, limitations, release notes |

## Testing

```bash
npm run lint
cd backend && python -m pytest
cd frontend && npm run build && npm run typecheck
npx playwright test tests/e2e/
```
