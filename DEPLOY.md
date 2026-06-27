---
last_verified: 2026-06-27T00:00:00Z
git_ref: master
verified_by: prod documentation refresh
---

# DEPLOY.md — Employed

This is the deployment source of truth for Employed production.

## Identity

| Field | Value |
|---|---|
| Repo | `xibodev/employed` |
| Product | Employed |
| Production branch | `master` |
| Integration branch | `uat` |
| Production domain | `joinemployed.com` |
| API health | `https://api.joinemployed.com/health` |

## Production surfaces

- Frontend: Vercel project `selo-pro/employed`, Next.js 15.5.19 standalone.
- Frontend hosts: `joinemployed.com`, `www.joinemployed.com`, `mx.joinemployed.com`, `mz.joinemployed.com`.
- API host: `api.joinemployed.com` through Cloudflare Tunnel to the EC2 Compose `api:8000` service.
- Backend runtime: one AWS Graviton `t4g.small` EC2 instance in us-east-1 with no inbound public ports.
- Database: RDS PostgreSQL 17, `db.t4g.micro`, Single-AZ, encrypted, deletion-protected.

## Infrastructure deployment

Infrastructure is Python CDK in `infrastructure/` and is deployed with explicit context:

```bash
cd infrastructure
npx aws-cdk@latest -a "python app.py" synth -c account=<account> -c region=us-east-1
npx aws-cdk@latest -a "python app.py" deploy --all -c account=<account> -c region=us-east-1
```

The CDK app defines five stacks: `Employed-Governance`, `Employed-Network-prod`, `Employed-Database-prod`, `Employed-Budget-prod`, and `Employed-Compute-prod`. Every resource is tagged `Product=employed`, `CostCenter=employed-prod`, `Env=prod`, `ManagedBy=cdk`.

## Backend production deployment

Workflow: `.github/workflows/deploy-prod.yml`.

Triggers: manual `workflow_dispatch` and tags matching `v*`.

Deployment chain:

1. Run the reusable CI gate.
2. Validate required SSM parameters from `deploy/ec2/required-secrets.txt`.
3. Build the API image for `linux/arm64`.
4. Push ECR tags `:prod` and `:prod-<sha>` to `868216907752.dkr.ecr.us-east-1.amazonaws.com/employed-api`.
5. Upload `deploy/ec2/*` to the deploy-assets S3 bucket.
6. Set SSM parameter `DEPLOY_IMAGE_TAG`.
7. Run SSM Run Command on the EC2 instance to rerun `bootstrap.sh`.
8. `bootstrap.sh` logs into ECR, renders `/opt/employed/.env` from SSM, pulls the image, runs `alembic upgrade head`, starts Compose, and gates on health.
9. The workflow smokes `https://api.joinemployed.com/health`.

Production deploy uses GitHub OIDC through repo secret `AWS_DEPLOY_ROLE_ARN`. No long-lived AWS keys are used.

## Frontend production deployment

Workflow: `.github/workflows/deploy-vercel.yml`.

Triggers: manual `workflow_dispatch` and release tags. Required repo secrets are `VERCEL_TOKEN`, `VERCEL_ORG_ID`, and `VERCEL_PROJECT_ID`.

Build-time public env:

- `NEXT_PUBLIC_API_URL=https://api.joinemployed.com`
- `NEXT_PUBLIC_APP_URL=https://joinemployed.com`
- `NEXT_PUBLIC_RECAPTCHA_SITE_KEY=<v3 site key>`

## Rollback

Backend rollback uses an existing immutable ECR tag:

1. Choose the prior known-good `prod-<sha>` image tag.
2. Re-run the production deployment workflow with that tag as `DEPLOY_IMAGE_TAG` or set the SSM parameter to that tag and rerun the SSM deploy command.
3. Confirm `https://api.joinemployed.com/health` returns healthy.

Frontend rollback uses Vercel's deployment rollback for the `selo-pro/employed` project or a redeploy of the prior commit/tag.

## Retired deployment

The old shared-VPS UAT deployment is disabled. Its DNS records, containers, volumes, application directory, and reverse-proxy vhosts are not part of current Employed topology. `.github/workflows/deploy-uat.yml` is disabled.
