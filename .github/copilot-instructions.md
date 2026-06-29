# Copilot Instructions — Employed

## Project

Employed is a trust-centric, integration-ready hiring platform for Mozambique (MZ) and Mexico (MX) built on FastAPI + Next.js 15. Frontend code is in `frontend/`; backend code is in `backend/`; production AWS infrastructure is in `infrastructure/`; EC2 runtime assets are in `deploy/ec2/`.

Production is live at `joinemployed.com`. The Vercel frontend serves `joinemployed.com`, `www.joinemployed.com`, `mx.joinemployed.com`, and `mz.joinemployed.com`. The API host `api.joinemployed.com` reaches the AWS EC2 backend through Cloudflare Tunnel. The retired shared-VPS UAT deployment is disabled and is not part of current topology.

## Mandatory rules (self-contained)

1. **No AI authorship trailers** — no `Co-Authored-By` lines and no generated-by footers.
2. **Never paste credentials** — reference names and paths, not values.
3. **Locale codes** — `en`, `pt`, `es` only.
4. **Env var naming** — use standard names: `SENTRY_DSN`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `FROM_EMAIL`, `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_APP_URL`, `FRONTEND_BASE_URL`, `RESUME_STORAGE_BACKEND`, `RESUME_S3_BUCKET`.
5. **Secrets posture** — production secrets are SSM SecureStrings under `/employed/prod/*`; required names are in `deploy/ec2/required-secrets.txt`.
6. **Runtime config** — mutable domain/provider values are config, not source constants.

## Key files

- `backend/app/main.py` — FastAPI app entrypoint and router wiring.
- `backend/app/config.py` — backend settings.
- `backend/app/routers/` — API route modules.
- `backend/app/services/` — business logic.
- `backend/app/models/` — SQLAlchemy models.
- `backend/alembic/versions/` — append-only migrations `001`-`005`.
- `frontend/src/lib/api.ts` — frontend API client base URL handling.
- `frontend/src/lib/market.ts` — hostname/subdomain market resolution.
- `frontend/src/lib/tenant.ts` — active company context.
- `deploy/ec2/` — EC2 bootstrap, Docker Compose, env rendering, required-secret list.
- `infrastructure/` — Python CDK stacks for ECR, OIDC, VPC, RDS, budget, EC2, AppRegistry.
- `.github/workflows/deploy-prod.yml` — backend production CD to ECR + EC2 via OIDC and SSM Run Command.
- `.github/workflows/deploy-vercel.yml` — frontend CD to Vercel.

## Hiring-platform conventions

1. **Layering.** API routes go in `routers/`; business logic in `services/`; validation in `schemas/`; models extend `Base` in `models/`.
2. **Authorization is permission-based.** Check permission strings via `services/rbac.py#require_permission`; do not gate by role name alone.
3. **Market vs tenant are orthogonal.** Market is resolved from hostname; tenant is resolved from company membership/resource scope.
4. **Verification is one shared state machine.** Use `services/verification.py#transition` and append audit rows.
5. **Audit + profile versions are append-only.** Do not add update/delete paths for `AuditLog` or `ProfileVersion`.
6. **Background work uses arq, not Celery.** PDF resume rendering and webhook delivery are arq tasks.
7. **Standard schemas at boundaries.** Use JSON Resume, schema.org `JobPosting`, normalized Application objects, and `external_refs`.
8. **Migrations are append-only.** Add new revisions; never edit migrations `001`-`005`.

## Production deployment

- `master` is the production source branch; `uat` is the integration branch.
- `deploy-prod.yml` runs CI, validates SSM required parameters, builds a linux/arm64 API image, pushes ECR tags `:prod` and `:prod-<sha>`, uploads `deploy/ec2/*` to the deploy-assets S3 bucket, sets `DEPLOY_IMAGE_TAG`, runs SSM Run Command on the EC2 instance, applies Alembic migrations, restarts Compose, and smokes `https://api.joinemployed.com/health`.
- `deploy-vercel.yml` deploys the frontend to Vercel with `NEXT_PUBLIC_API_URL=https://api.joinemployed.com`, `NEXT_PUBLIC_APP_URL=https://joinemployed.com`, and the reCAPTCHA site key.
- `deploy-uat.yml` is disabled; its old GHCR images and shared-VPS hosts are retired.

## Commands

```bash
npm run lint
cd backend && python -m pytest
cd frontend && npm run build
cd frontend && npm run typecheck
npx playwright test tests/e2e/
npx aws-cdk@latest -a "python app.py" synth -c account=<account> -c region=us-east-1
```
