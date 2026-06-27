---
last_verified: 2026-06-27T00:00:00Z
git_ref: master
verified_by: prod documentation refresh
---

# Config & Secrets Map — Employed

This map names variables and storage locations only. It never records secret values.

## Production source of truth

Production runtime configuration lives in SSM Parameter Store under `/employed/prod/*`. Secret values are SecureStrings. Employed does not use AWS Secrets Manager. `deploy/ec2/required-secrets.txt` is the canonical required list, and `deploy/ec2/render-env.sh` renders `/opt/employed/.env` for Docker Compose.

## SSM parameters

| Parameter suffix | Secret? | Purpose |
|------------------|---------|---------|
| `db-master-password` | yes | RDS master password referenced by CDK through an SSM secure dynamic reference |
| `DATABASE_URL` | yes | SQLAlchemy/Alembic database URL |
| `SECRET_KEY` | yes | JWT signing key |
| `IP_SALT` | yes | Salt for IP/MSISDN hashing |
| `STRIPE_SECRET_KEY` | yes | Stripe test-mode secret key |
| `STRIPE_PUBLISHABLE_KEY` | no | Stripe publishable key |
| `STRIPE_WEBHOOK_SECRET` | yes | Stripe webhook signing secret |
| `GOOGLE_CLIENT_ID` | no | Google OAuth client id |
| `GOOGLE_CLIENT_SECRET` | yes | Google OAuth secret |
| `NEXT_PUBLIC_RECAPTCHA_SITE_KEY` | no | reCAPTCHA v3 site key |
| `RECAPTCHA_SECRET_KEY` | yes | reCAPTCHA v3 server secret |
| `SMTP_USERNAME` | yes | AWS SES SMTP username |
| `SMTP_PASSWORD` | yes | AWS SES SMTP password |
| `CLOUDFLARED_TOKEN` | yes | Cloudflare Tunnel token |
| `DEPLOY_ASSETS_BUCKET` | no | S3 bucket used for EC2 deploy assets |
| `DEPLOY_IMAGE_TAG` | no | ECR image tag to deploy |

## Rendered backend env

| Variable | Consumer | Notes |
|----------|----------|-------|
| `ENVIRONMENT` | backend settings | `production` in prod |
| `DATABASE_URL` / `ALEMBIC_DATABASE_URL` | SQLAlchemy/Alembic | RDS PostgreSQL 17 |
| `REDIS_URL` | backend/worker | Compose sidecar Redis |
| `SECRET_KEY` | JWT | required outside dev/test |
| `IP_SALT` | hashing | required in prod |
| `CORS_ORIGINS` | API CORS | exact production frontend origins |
| `FRONTEND_BASE_URL` | email links | `https://joinemployed.com` |
| `NEXT_PUBLIC_APP_URL` | frontend/server helpers | `https://joinemployed.com` |
| `NEXT_PUBLIC_API_URL` | frontend API client | `https://api.joinemployed.com` |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | OAuth | Google web client |
| `RECAPTCHA_SECRET_KEY` / `NEXT_PUBLIC_RECAPTCHA_SITE_KEY` | bot protection | reCAPTCHA v3 |
| `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` / `STRIPE_PUBLISHABLE_KEY` | payments | Stripe test mode |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_USE_TLS` / `FROM_EMAIL` | email | AWS SES, sender `noreply@joinemployed.com` |
| `RESUME_ARTIFACT_DIR` | arq resume PDF task | local ephemeral directory on EC2 |
| `SENTRY_DSN` / `SENTRY_ENVIRONMENT` / `SENTRY_TRACES_SAMPLE_RATE` | Bugsink-compatible SDKs | DSN empty means no-op |

## Vercel build-time env

| Variable | Value |
|----------|-------|
| `NEXT_PUBLIC_API_URL` | `https://api.joinemployed.com` |
| `NEXT_PUBLIC_APP_URL` | `https://joinemployed.com` |
| `NEXT_PUBLIC_RECAPTCHA_SITE_KEY` | reCAPTCHA v3 public site key |

## Local and CI

Local dev uses repo examples and developer-local `.env` files. CI uses workflow-provided test values with Postgres 16 and Redis 7 service containers.
