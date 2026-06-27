---
last_verified: 2026-06-27T00:00:00Z
git_ref: master
verified_by: prod documentation refresh
---

# Deployment Topology — Employed

Employed production is a split Vercel + AWS + Cloudflare deployment for `joinemployed.com`.

## Environments

| Env | Status | Where |
|-----|--------|-------|
| Production | live | Vercel frontend + AWS us-east-1 EC2/RDS backend + Cloudflare DNS/Tunnel |
| Integration | source branch only | `uat` branch; old shared-VPS UAT deployment is disabled |
| Local dev/test | developer machine | Docker Compose overlays and local process runs |

## Public ingress

| Host | Market / role | Target |
|------|---------------|--------|
| `joinemployed.com` | MZ default | Vercel frontend |
| `www.joinemployed.com` | canonical www | Vercel frontend |
| `mz.joinemployed.com` | MZ market | Vercel frontend |
| `mx.joinemployed.com` | MX market | Vercel frontend |
| `api.joinemployed.com` | FastAPI API | Cloudflare Tunnel to EC2 Compose service `api:8000` |

Cloudflare Registrar/DNS manages `joinemployed.com`. Cloudflare Tunnel dials out from the EC2 instance, so the instance has no public inbound application ports, no Elastic IP, no ALB, and no Fargate service.

## Runtime graph

```text
browser
  ├─ HTTPS joinemployed.com / www / mz / mx ──► Vercel Next.js 15.5.19 standalone
  │                                                │
  │                                                └─ API calls to https://api.joinemployed.com
  └─ HTTPS api.joinemployed.com ──► Cloudflare Tunnel ──► EC2 Docker Compose
                                                            ├─ api: FastAPI/uvicorn :8000
                                                            ├─ worker: arq
                                                            ├─ redis: sidecar
                                                            └─ cloudflared: tunnel
                                                                  │
                                                                  ▼
                                                            RDS PostgreSQL 17
```

Resume PDF artifacts write to local `RESUME_ARTIFACT_DIR` on the EC2 host. Employed has no production application object-storage bucket. The only S3 bucket in production is `employed-prod-deploy-assets-*`, used for deploy asset delivery to the EC2 instance.

## AWS infrastructure

AWS account `868216907752` (`thibit`), region `us-east-1`, hosts Employed in isolated product infrastructure inside a shared account.

Five CDK stacks define production:

| Stack | Purpose |
|-------|---------|
| `Employed-Governance` | ECR repo `employed-api`, GitHub OIDC deploy role, account/app governance, AppRegistry application `Employed`, product budget and account tripwire |
| `Employed-Network-prod` | VPC `10.1.0.0/16`, two AZs, no NAT, public and private-isolated subnets, service and RDS security groups |
| `Employed-Database-prod` | RDS PostgreSQL 17 `db.t4g.micro`, Single-AZ, gp3 20 GB, private, encrypted, deletion-protected |
| `Employed-Budget-prod` | $80/month product budget with tiered alerts and a deny-new-spend deploy-role policy at 100% |
| `Employed-Compute-prod` | EC2 `t4g.small` with IMDSv2, ECR pull, SSM read, SES send, deploy-assets S3 read, and `bootstrap.sh` user data |

Every resource is tagged `Product=employed`, `CostCenter=employed-prod`, `Env=prod`, `ManagedBy=cdk`.

## Images

| Image | Registry | Tags | Consumers |
|-------|----------|------|-----------|
| API/runtime | Amazon ECR `868216907752.dkr.ecr.us-east-1.amazonaws.com/employed-api` | `prod`, `prod-<sha>` | `api`, `worker`, migration step |

The retired GHCR UAT images are not production artifacts.

## CI/CD

| Workflow | Trigger | Role |
|----------|---------|------|
| `.github/workflows/ci.yml` | reusable `workflow_call`, push to `main`/`master`, PR | backend Ruff check/format + pytest with Postgres 16 and Redis 7; frontend ESLint + TypeScript + Next build |
| `.github/workflows/deploy-prod.yml` | `workflow_dispatch`, tags `v*` | CI gate, SSM secret validation, ECR build/push, deploy-assets upload, SSM `DEPLOY_IMAGE_TAG`, EC2 SSM Run Command, public smoke |
| `.github/workflows/deploy-vercel.yml` | `workflow_dispatch`, tags | Vercel frontend deployment |
| `.github/workflows/deploy-uat.yml` | disabled | retired UAT pipeline |

## Secrets and config

Runtime secrets are SSM SecureStrings under `/employed/prod/*`. `deploy/ec2/render-env.sh` renders `/opt/employed/.env` from SSM at deploy time. `deploy/ec2/required-secrets.txt` is the canonical pre-deploy validation list.

## Observability

`SENTRY_DSN` is the Bugsink-compatible error-tracking hook. It is empty in production, so SDKs no-op. Gatus is the uptime standard; production URL monitors are still an operational follow-up.
