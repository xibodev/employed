# Employed — single-EC2 production API runtime

This directory is the reproducible runtime for Employed's backend API on **one EC2 box** via `docker compose`, fronted by a **Cloudflare Tunnel**. The frontend is served by **Vercel** at `joinemployed.com`, so this stack runs only:

- `redis`
- `api`
- `worker`
- `cloudflared`

The tunnel routes only `api.joinemployed.com -> http://api:8000`. The apex `joinemployed.com` is intentionally outside this compose stack.

## Files

- `docker-compose.ec2.yml` — the runtime: `redis` + `api` + `worker` + `cloudflared`.
- `render-env.sh` — assembles `/opt/employed/.env` from SSM `/employed/prod/*` + static production defaults.
- `bootstrap.sh` — EC2 user-data: installs Docker + Compose, pulls these assets from the deploy-assets S3 bucket, renders `.env`, and starts Docker Compose.

## One-time prerequisites (thibit account, `us-east-1`)

1. **SSM params** under `/employed/prod/`:
   - Secrets/SecureStrings: `DATABASE_URL`, `SECRET_KEY`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PUBLISHABLE_KEY`, `IP_SALT`, `RECAPTCHA_SECRET_KEY`, `NEXT_PUBLIC_RECAPTCHA_SITE_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `CLOUDFLARED_TOKEN`, `SENTRY_DSN`, `RESUME_STORAGE_BACKEND`, `RESUME_S3_BUCKET`, `RESUME_S3_ENDPOINT_URL`, `RESUME_S3_ACCESS_KEY_ID`, `RESUME_S3_SECRET_ACCESS_KEY`, `RESUME_S3_REGION`.
   - Strings: `DEPLOY_IMAGE_TAG` (for example `prod-<sha>`), `DEPLOY_ASSETS_BUCKET`.
   - Optional overrides for static defaults: `REDIS_URL`, `JWT_ALGORITHM`, token TTLs, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USE_TLS`, `SMTP_USE_SSL`, `FROM_EMAIL`, `ADMIN_EMAIL`, `ENVIRONMENT`, public URLs, `CORS_ORIGINS`, `SENTRY_ENVIRONMENT`.
2. **Deploy-assets S3 bucket** holding `ec2/docker-compose.ec2.yml` + `ec2/render-env.sh`.
3. **IAM instance role** with: `AmazonSSMManagedInstanceCore`, `ssm:GetParameter` on `/employed/prod/*`, `kms:Decrypt` via SSM, ECR pull for `employed-api`, and `s3:GetObject` on the deploy-assets bucket.
4. **Security group** for the box, allowed on the RDS SG's 5432 ingress. No inbound application ports are required; cloudflared dials out.
5. **Cloudflare named tunnel** `employed-prod` with a public-hostname route `api.joinemployed.com -> http://api:8000`; its run token goes in SSM `CLOUDFLARED_TOKEN`.

## Provision

Launch an Amazon Linux 2023 instance in the Employed VPC public subnet with the instance role + SG above and `bootstrap.sh` as user-data. The box self-provisions into `/opt/employed`.

Manual bring-up when iterating:

```bash
cd /opt/employed
EMPLOYED_API_IMAGE=<ecr-image> ./render-env.sh
docker compose up -d
```

## Verify

```bash
docker compose ps
docker compose logs api --tail=100
curl -fsS -H 'Host: api.joinemployed.com' http://localhost:8000/health
```

Then verify `https://api.joinemployed.com/health` through Cloudflare Tunnel.
