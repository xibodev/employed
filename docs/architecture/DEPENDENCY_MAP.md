---
last_verified: 2026-06-27T00:00:00Z
git_ref: master
verified_by: prod documentation refresh
---

# Dependency Map — Employed

## Runtime dependencies

| Dependency | Role | Production state |
|------------|------|------------------|
| Vercel | Hosts the Next.js 15.5.19 standalone frontend | live project `selo-pro/employed` |
| Amazon ECR | Stores backend runtime image | `employed-api:prod` and `employed-api:prod-<sha>` |
| EC2 | Runs API, worker, Redis, Cloudflare Tunnel | one `t4g.small` ARM64 instance |
| RDS PostgreSQL 17 | Primary relational datastore | `db.t4g.micro`, Single-AZ, encrypted |
| Redis sidecar | arq queue, rate limiting, lockout, JTI revocation, replay cache | Compose service on EC2 |
| Cloudflare DNS/Tunnel | DNS, TLS edge, API ingress | `api.joinemployed.com` tunnel to EC2 |
| AWS SES | Transactional email | domain identity `joinemployed.com`, sender `noreply@joinemployed.com` |
| Stripe | Featured listing payments | test mode; prod webhook endpoint registered |
| M-Pesa / e-Mola | MZ mobile-money payment options | simulator mode |
| Google OAuth | Social sign-in | web client for apex/www origins and API callback |
| reCAPTCHA v3 | Anonymous job-posting abuse protection | domain `joinemployed.com` |
| Bugsink | Error tracking standard | SDK-compatible DSN variable exists; DSN empty so no-op |
| Gatus | Uptime standard | production monitors not yet wired |

## Backend packages

FastAPI/uvicorn serve the API. SQLAlchemy, psycopg2, and Alembic handle PostgreSQL. `arq` and `redis` power background jobs and distributed state. `stripe`, `httpx`, `bcrypt`, `python-jose`, `bleach`, and `pydantic-settings` support payments, external calls, auth, sanitization, and settings. `sentry-sdk[fastapi]` remains the Bugsink-compatible client and is DSN-gated.

## Frontend packages

Next.js 15.5.19, React 19, TypeScript, next-intl, Tailwind, TipTap, and reCAPTCHA v3 provide the web UI. `@sentry/nextjs` is DSN-gated for Bugsink-compatible error reporting.

## Internal edges

```text
frontend API client ──► FastAPI routers ──► services/models ──► RDS PostgreSQL
FastAPI/worker ───────► Redis sidecar
worker ───────────────► email, webhook, expiry, resume PDF tasks
payments routers ─────► Stripe / mobile-money simulators
OAuth/reCAPTCHA ──────► Google endpoints
email service ────────► AWS SES SMTP
observability SDKs ───► Bugsink when SENTRY_DSN is set
```

## Deployment dependencies

`deploy-prod.yml` depends on GitHub OIDC, ECR, SSM Parameter Store, S3 deploy-assets, SSM Run Command, and public smoke access to `https://api.joinemployed.com/health`. `deploy-vercel.yml` depends on Vercel project secrets and public build-time env.
