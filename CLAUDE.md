<!-- last_verified: 2026-06-27T00:00:00Z| git_ref: master| verified_by: prod documentation refresh -->

# Employed - Architecture Notes

Employed is a trust-centric, integration-ready hiring platform for Mozambique (MZ) and Mexico (MX). The product is live at `joinemployed.com`; the old `employed.co.mz` name is retired and is not a production domain.

## Current production

- Repository: `github.com/xibodev/employed`.
- Branches: `master` is the production source branch; `uat` is the integration branch.
- Frontend: Vercel project `selo-pro/employed`, Next.js 15.5.19 standalone, public hosts `joinemployed.com`, `www.joinemployed.com`, `mx.joinemployed.com`, and `mz.joinemployed.com`.
- API: `api.joinemployed.com` reaches the AWS EC2 backend through Cloudflare Tunnel; the instance exposes no inbound public ports.
- Backend runtime: one Amazon Linux 2023 ARM64 `t4g.small` running Docker Compose services `api`, `worker`, `redis`, and `cloudflared` from `deploy/ec2/` assets.
- Database: encrypted, deletion-protected RDS PostgreSQL 17 (`db.t4g.micro`, Single-AZ, gp3 20 GB) in private subnets.
- Secrets: SSM Parameter Store SecureStrings under `/employed/prod/*`; no application secrets are stored in the repo.
- Email: AWS SES for `joinemployed.com`, sender `noreply@joinemployed.com`.
- Observability standard: Bugsink via `SENTRY_DSN` and Gatus uptime checks. Both are the house standard; production URL monitors/DSN are still open operational items.

## Technology stack

- Backend: FastAPI, SQLAlchemy, Alembic, arq, Redis sidecar.
- Frontend: Next.js 15.5.19, React 19, TypeScript.
- Data layer: PostgreSQL 17 in production; Alembic migrations `001`-`005` are append-only.
- Payments: Stripe test mode; M-Pesa and e-Mola simulator mode.
- Auth/bot protection: email/password, Google OAuth, reCAPTCHA v3.

## Application structure

```text
/backend         FastAPI app, models, routers, workers, migrations, pytest suite
/frontend        Next.js app router frontend
/deploy/ec2      EC2 bootstrap, compose, env rendering, required-secret list
/infrastructure  Python CDK stacks for production AWS infrastructure
/docs            API, architecture, operations, product, ADRs
/tests           Playwright E2E coverage
/public          Static assets shared at repo level
```

## Current product scope

- Market-localized public job listings: apex and `mz.*` map to MZ, `mx.*` maps to MX.
- Companies, memberships, and two-layer permission-based RBAC.
- Shared verification state machine and composable trust badges.
- JSON Resume profile versioning and first-class application pipeline.
- Append-only audit log, outbound webhooks, and versioned `/export/v1` API.
- 90-day listing expiration and arq background work.
- Locales: `en`, `pt`, `es` only.

## Commands

```bash
npm run lint
cd backend && python -m pytest
cd frontend && npm run build
cd frontend && npm run typecheck
npx playwright test tests/e2e/
npx aws-cdk@latest -a "python app.py" deploy -c account=<account> -c region=us-east-1
```

## AI assistant rules

- No AI authorship trailers in docs or commits.
- Do not paste or commit secret values. Reference secret names and files only.
- Keep production facts present-tense; changelog narration belongs in `CHANGELOG.md`, `docs/product/RELEASE_NOTES.md`, `docs/product/BACKLOG.md`, `TODO.md`, or `docs/archive/**`.
- Market and tenant are orthogonal; never derive company tenancy from hostname.
