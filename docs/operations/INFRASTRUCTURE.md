<!-- last_verified: 2026-06-28T00:00:00Z| git_ref: master| verified_by: prod documentation refresh -->

# Infrastructure & Operating Context — Employed

This repository is self-contained. It documents the current production topology for Employed at `joinemployed.com`.

## Deployment targets

| Surface | Current state |
|---|---|
| Frontend | Vercel project `selo-pro/employed`, Next.js 15.5.19 standalone |
| Backend | AWS EC2 `t4g.small` ARM64, Amazon Linux 2023, Docker Compose |
| Database | RDS PostgreSQL 17 `db.t4g.micro`, Single-AZ, gp3 20 GB, private, encrypted, deletion-protected |
| Ingress | Cloudflare DNS and Tunnel; no public inbound EC2 application ports |
| Account/region | AWS account `868216907752` (`thibit`), `us-east-1` |

The old shared-VPS UAT deployment is retired and disabled.

## Domains

| Host | Role |
|------|------|
| `joinemployed.com` | production frontend, MZ default |
| `www.joinemployed.com` | production frontend alias |
| `mz.joinemployed.com` | MZ market frontend |
| `mx.joinemployed.com` | MX market frontend |
| `api.joinemployed.com` | production API through Cloudflare Tunnel |

The old `employed.co.mz` name is retired and is not a production domain.

## AWS CDK stacks

- `Employed-Governance`: ECR repo, GitHub OIDC deploy role, budgets, AppRegistry application.
- `Employed-Network-prod`: isolated VPC `10.1.0.0/16`, two AZs, no NAT.
- `Employed-Database-prod`: RDS PostgreSQL 17.
- `Employed-Budget-prod`: $80/month budget and deploy-role deny-new-spend kill-switch at 100%.
- `Employed-Compute-prod`: EC2 runtime instance, IAM role, user data.

Estimated on-demand cost is about $31-34/month before credits.

## Runtime services

The EC2 host runs Docker Compose from `deploy/ec2/docker-compose.ec2.yml`:

- `api`: FastAPI/uvicorn on container port 8000, run with `--proxy-headers --forwarded-allow-ips=*` so Cloudflare Tunnel forwarded headers build correct external URLs.
- `worker`: arq worker.
- `redis`: sidecar for queues, rate limits, lockout, token revocation, replay cache.
- `cloudflared`: tunnel to `api.joinemployed.com`.

## Secrets boundary

Production secrets are SSM Parameter Store SecureStrings under `/employed/prod/*`. The repo stores names and scripts only, never values. Employed does not use AWS Secrets Manager.

Required production names are maintained in `deploy/ec2/required-secrets.txt` and include database, JWT, IP salt, Stripe, Google OAuth, reCAPTCHA, SES SMTP, Cloudflare Tunnel, `SENTRY_DSN`, R2 resume-storage parameters (`RESUME_STORAGE_BACKEND`, `RESUME_S3_BUCKET`, `RESUME_S3_ENDPOINT_URL`, `RESUME_S3_ACCESS_KEY_ID`, `RESUME_S3_SECRET_ACCESS_KEY`, `RESUME_S3_REGION`), and deploy image/bucket parameters. `render-env.sh` assembles `/opt/employed/.env` from SSM on every deploy.

## Email

Transactional email uses AWS SES for `joinemployed.com` with Easy DKIM. The sender is `noreply@joinemployed.com`. SMTP credentials live in SSM SecureStrings.

## Object storage

Resume PDF artifacts persist durably to Cloudflare R2 bucket `employed-prod-resumes` via `app/services/resume_storage.py` (boto3, `RESUME_STORAGE_BACKEND=r2`). `build_resume_artifact` uploads to R2 when configured and falls back to local disk for dev/test. A user-facing download route is not yet wired. The deploy-assets S3 bucket is only deployment plumbing.

## Observability

- Error tracking: Bugsink is live. Project `employed-api` (id 11) at `https://errors.xibodev.com`; backend `SENTRY_DSN` is set in SSM and initialises in `production`.
- Uptime: Gatus is live and monitors `joinemployed.com`, www/mx/mz, and `api.joinemployed.com/health` (atlas-driven group "Employed").

All 61 Employed AWS resources carry tags `Product=employed`, `CostCenter=employed-prod`, `Env=prod`, `ManagedBy=cdk`. The CDK aspect `TagLaunchTemplateLaunchedResources` (`infrastructure/app.py`) tags launch-template instance/volume/ENI.

## CI/CD

- `ci.yml`: backend Ruff + pytest, frontend ESLint + TypeScript + build.
- `deploy-prod.yml`: OIDC to AWS, ECR image build/push, SSM validation, EC2 SSM deployment, smoke test.
- `deploy-vercel.yml`: Vercel frontend deployment.
- `deploy-uat.yml`: disabled retired pipeline.
