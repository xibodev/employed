---
last_verified: 2026-06-27T00:00:00Z
git_ref: master
verified_by: prod documentation refresh
---

# Repo Map — Employed

Employed is a monorepo for the FastAPI backend, Next.js frontend, production CDK infrastructure, EC2 deployment assets, tests, and documentation.

## Top-level layout

| Path | Purpose |
|------|---------|
| `backend/` | FastAPI app, SQLAlchemy models, routers, services, arq workers, Alembic migrations, pytest suite |
| `frontend/` | Next.js 15.5.19 App Router frontend, market helpers, tenant context, UI components |
| `deploy/` | Docker and deployment support |
| `deploy/ec2/` | Production EC2 bootstrap, Compose file, env renderer, required SSM parameter list |
| `infrastructure/` | Python CDK app defining governance, network, database, budget, and compute stacks |
| `.github/workflows/` | CI, production ECR/EC2 deploy, Vercel deploy, disabled retired UAT workflow |
| `docs/` | Architecture, operations, product, API, ADR, and runbook documentation |
| `tests/` | Playwright E2E suites |
| `quality/` | Quality-run personas/journeys/service inventories |
| `scripts/` | Local tooling and audits |
| `brand/`, `design/`, `public/` | Brand, design previews, static assets |

## Deployable surfaces

| Surface | Entry point | Production runtime |
|---------|-------------|--------------------|
| API | `backend/app/main.py` | EC2 Compose `api`, uvicorn :8000 |
| Worker | `backend/app/workers/config.py` | EC2 Compose `worker`, arq |
| Migrations | `backend/alembic.ini` | deploy-time `alembic upgrade head` |
| Frontend | Next.js standalone server | Vercel project `selo-pro/employed` |
| Infrastructure | `infrastructure/app.py` | CDK stacks in AWS us-east-1 |

## Key backend areas

- `app/config.py`: env-driven settings.
- `app/middleware/market.py`: market resolution from forwarded host/host.
- `app/auth/`: JWT, dependencies, OAuth, passwords, revocation.
- `app/routers/`: public and authenticated API routes.
- `app/services/`: business rules and integration logic.
- `app/workers/`: arq worker and tasks.
- `alembic/versions/`: append-only migrations.

## Key frontend areas

- `src/app/`: App Router pages and API health route.
- `src/lib/api.ts`: API client and forwarded-host handling.
- `src/lib/market.ts`: market host derivation from `NEXT_PUBLIC_APP_URL`.
- `src/lib/tenant.ts`: company/tenant state helpers.
- `src/contexts/`: auth and tenant contexts.
- `messages/`: `en`, `pt`, `es` catalogs.

## Caution areas

- Do not edit migrations `001`-`005`; add a new revision.
- Do not hardcode production domains in source; use config/env helpers.
- Do not store secret values in docs, examples, or code.
- Do not alter CI/CD behavior in documentation-only work.
