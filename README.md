<!-- last_verified: 2026-06-19T00:00:00Z | git_ref: uat (multi-tenant-hiring-platform complete) | verified_by: full implementation doc refresh -->

# Employed

Employed is a trust-centric, integration-ready hiring platform for Mozambique and Mexico: *more than a job board, less than a heavy ATS*.

Built on FastAPI + Next.js, it combines the core job board functionality (companies post roles, candidates browse opportunities, admins moderate listings) with advanced hiring platform features: multi-tenant companies and memberships, a two-layer RBAC permission system, per-entity verification with composable trust badges, version-controlled JSON Resume profiles, a lightweight applications pipeline, an append-only audit trail, outbound webhooks, and a versioned export API exposing standard schemas. Market (geography/locale/payment) and tenant (organization) remain orthogonal axes.

## Core Features

### Trust & Verification System
- **Per-entity verification state machine** with states: unverified → pending → verified/rejected/revoked/flagged
- **Composable trust badges** (domain verified, business-document verified, email verified, etc.) — no single numeric score
- **Low-friction domain verification** via DNS TXT records or matching member emails
- **Manual business-document verification** for higher trust tiers

### Multi-Tenant Organization Management
- **Company entities** with unique slugs per market, verification status, and trust badges
- **Membership system** linking users to companies with tenant-scoped roles (org_owner, org_admin, recruiter, member)
- **Two-layer RBAC** with platform-level and tenant-level permissions
- **Domain auto-membership** for verified company email domains

### Applications Pipeline
- **First-class Application entity** with tracked pipeline stages: applied → reviewed → shortlisted → rejected → hired
- **Version-controlled candidate profiles** using JSON Resume standard with immutable snapshots
- **Recruiter management interface** with list and kanban board views
- **Email templates** with token substitution for application communications
- **Dual application channels**: tracked pipeline (default) + email-apply (always available)

### Integration & Export
- **Versioned export API** returning candidates in JSON Resume format, jobs in schema.org JobPosting JSON-LD
- **External references** JSONB field on all major entities for mapping to external ATS IDs
- **Outbound webhooks** for key events (job.published, application.created, application.status_changed)
- **Standard schemas** at all integration boundaries to prevent lock-in

### Audit & Compliance
- **Append-only audit trail** capturing all privileged, verification, and moderation actions
- **Immutable profile versions** that can never be modified after creation
- **Actor tracking** with support for both user actors and system actors
- **Before/after state** capture for all changes

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