<!-- last_verified: 2026-06-27T00:00:00Z| git_ref: master| verified_by: prod documentation refresh -->

# Employed — Services

Canonical current-state document for Employed.

## Product

Employed is a multilingual hiring platform for Mozambique and Mexico. Companies post jobs, candidates browse localized listings, recruiters manage applications, and admins moderate/verifiy trusted entities.

## Repository

| Surface | Repo | Path |
|---------|------|------|
| Product monorepo | `xibodev/employed` | repo root |
| Backend API | same repo | `backend/` |
| Frontend | same repo | `frontend/` |
| Infrastructure | same repo | `infrastructure/` |
| EC2 runtime assets | same repo | `deploy/ec2/` |

## Live production

| Surface | State |
|---------|-------|
| Frontend | Live on Vercel project `selo-pro/employed` at `joinemployed.com`, `www.joinemployed.com`, `mx.joinemployed.com`, `mz.joinemployed.com` |
| Backend API | Live at `https://api.joinemployed.com` through Cloudflare Tunnel to EC2 Compose `api:8000` |
| Health | `https://api.joinemployed.com/health` |
| Database | RDS PostgreSQL 17, `db.t4g.micro`, Single-AZ, encrypted, private |
| Worker | arq worker in EC2 Compose |
| Redis | EC2 Compose sidecar |
| Email | AWS SES for `joinemployed.com`, sender `noreply@joinemployed.com` |
| Secrets | SSM SecureStrings under `/employed/prod/*` |
| UAT | old shared-VPS deployment is retired; `deploy-uat.yml` is disabled |

## Hosts and market behavior

| Host | Market | Default locale |
|------|--------|----------------|
| `joinemployed.com` | MZ | `pt` |
| `www.joinemployed.com` | MZ | `pt` |
| `mz.joinemployed.com` | MZ | `pt` |
| `mx.joinemployed.com` | MX | `es` |
| `api.joinemployed.com` | API | n/a |

## External APIs

| Service | Current state |
|---------|---------------|
| Stripe | Test mode; webhook endpoint registered at `https://api.joinemployed.com/_stripe/webhook` |
| M-Pesa / e-Mola | Simulator mode |
| Google OAuth | Web client covers apex/www origins and `https://api.joinemployed.com/auth/oauth/google/callback` |
| reCAPTCHA v3 | Domain `joinemployed.com` |
| Bugsink | Standard error sink; `SENTRY_DSN` is empty so SDKs no-op |
| Gatus | Standard uptime monitor; production URL checks are not wired yet |

## CI/CD

| Workflow | Role |
|----------|------|
| `ci.yml` | Backend Ruff/pytest and frontend ESLint/TypeScript/build |
| `deploy-prod.yml` | Backend production deploy to ECR + EC2 through OIDC and SSM Run Command |
| `deploy-vercel.yml` | Frontend deploy to Vercel |
| `deploy-uat.yml` | Disabled retired UAT workflow |

## Open operational follow-ups

- Set Bugsink DSNs and `SENTRY_ENVIRONMENT=production`.
- Add Gatus checks for `joinemployed.com` and `api.joinemployed.com/health`.
- Add Google OAuth/reCAPTCHA coverage for `mx.joinemployed.com` and `mz.joinemployed.com` if those hosts require direct sign-in flows.
- Switch Stripe from test mode to live keys when monetisation starts.
- Move resume artifacts to persistent media storage when durable PDFs are required.
