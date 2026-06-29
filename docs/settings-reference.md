---
last_verified: 2026-06-28T00:00:00Z
git_ref: master
verified_by: prod documentation refresh
---

# Settings Reference

Environment variable reference for the FastAPI backend and Next.js frontend. Production values resolve from SSM SecureStrings under `/employed/prod/*` and Vercel environment settings. See `docs/architecture/CONFIG_AND_SECRETS_MAP.md` for the full map.

## Core

| Variable | Required | Description |
|----------|----------|-------------|
| `ENVIRONMENT` | yes | `production` in prod |
| `SECRET_KEY` / `JWT_SECRET_KEY` | yes outside dev/test | JWT signing key |
| `IP_SALT` | yes | Salt for hashed IP/MSISDN values |
| `LOG_LEVEL` | no | Python logging level |
| `DEBUG` | no | Must be false in production |

## Database and Redis

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | yes | RDS PostgreSQL 17 URL |
| `ALEMBIC_DATABASE_URL` | no | Falls back to `DATABASE_URL` |
| `DATABASE_POOL_SIZE` / `DATABASE_MAX_OVERFLOW` / `DATABASE_POOL_TIMEOUT` / `DATABASE_POOL_RECYCLE` | no | SQLAlchemy pool tuning |
| `REDIS_URL` | yes in prod | Compose sidecar Redis URL |

## Network and app URLs

| Variable | Required | Production value |
|----------|----------|------------------|
| `NEXT_PUBLIC_API_URL` | yes | `https://api.joinemployed.com` |
| `NEXT_PUBLIC_APP_URL` | yes | `https://joinemployed.com` |
| `FRONTEND_BASE_URL` | yes | `https://joinemployed.com` |
| `CORS_ORIGINS` | yes outside dev | exact Vercel frontend origins |
| `TRUSTED_PROXY_IPS` | no | trusted proxy ranges for client-IP resolution |

## Email

| Variable | Required | Description |
|----------|----------|-------------|
| `SMTP_HOST` | yes for email | AWS SES SMTP endpoint |
| `SMTP_PORT` | yes for email | SES SMTP port |
| `SMTP_USERNAME` | yes for email | SES SMTP username |
| `SMTP_PASSWORD` | yes for email | SES SMTP password |
| `SMTP_USE_TLS` / `SMTP_USE_SSL` | no | SMTP transport mode |
| `FROM_EMAIL` | yes for email | `noreply@joinemployed.com` |
| `ADMIN_EMAIL` | no | operator notification recipient |

## Auth and bot protection

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | yes for Google OAuth | Google web client |
| `RECAPTCHA_SECRET_KEY` | yes for anonymous posting | server verify key |
| `NEXT_PUBLIC_RECAPTCHA_SITE_KEY` | yes for widget | browser site key |
| `RECAPTCHA_MIN_SCORE` | no | score threshold |
| `RECAPTCHA_BYPASS_IN_DEVELOPMENT` | no | dev/test-only bypass |

## Payments

| Variable | Required | Description |
|----------|----------|-------------|
| `STRIPE_SECRET_KEY` | yes for Stripe | test-mode key currently |
| `STRIPE_WEBHOOK_SECRET` | yes for webhooks | Stripe webhook signature secret |
| `STRIPE_PUBLISHABLE_KEY` | yes for client checkout | publishable key |
| `MPESA_SIMULATOR` / `EMOLA_SIMULATOR` | no | simulator flags |
| `MPESA_WEBHOOK_SECRET` / `EMOLA_WEBHOOK_SECRET` | live mode only | mobile-money HMAC secrets |

## Observability

| Variable | Required | Description |
|----------|----------|-------------|
| `SENTRY_DSN` | no | Bugsink DSN; set in prod, error tracking active |
| `NEXT_PUBLIC_SENTRY_DSN` | no | browser Bugsink DSN if enabled |
| `SENTRY_ENVIRONMENT` | no | `production` in prod |
| `SENTRY_TRACES_SAMPLE_RATE` | no | optional tracing sample rate |

## Worker and artifacts

| Variable | Required | Description |
|----------|----------|-------------|
| `RESUME_STORAGE_BACKEND` | no | `r2` in prod; `local` fallback for dev/test |
| `RESUME_S3_BUCKET` / `RESUME_S3_ENDPOINT_URL` / `RESUME_S3_ACCESS_KEY_ID` / `RESUME_S3_SECRET_ACCESS_KEY` / `RESUME_S3_REGION` | r2 mode | Cloudflare R2 bucket `employed-prod-resumes` |
| `RESUME_ARTIFACT_DIR` | no | local resume PDF directory for dev/test fallback |
