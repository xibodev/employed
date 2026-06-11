---
last_verified: 2026-06-11T02:02:49Z
git_ref: fix/quality-run-2026-06-10 (uat baseline 00aa899)
verified_by: doc-drift audit, quality run 2026-06-10_120309
---

# DEPLOY.md — employed.co.mz

> Source of truth for this repo's deployment. Update when topology changes.
> Full observed-state detail: `docs/architecture/DEPLOYMENT_TOPOLOGY.md`.

## Identity

| Field | Value |
|---|---|
| Repo | `mekjr1/employed.co.mz` |
| Default branch | `master` (GitHub) — rename to `main` is an open TODO in `SERVICES.md` |
| Deploy branch | `uat` (push to `uat` triggers the deploy workflow) |
| Live UAT baseline | `uat` @ `00aa899` (branch `fix/quality-run-2026-06-10` is unmerged/undeployed) |

## Where deployed

- **Box**: `box3` (109.123.241.71)
- **Host ports (loopback only)**: `127.0.0.1:3300` (frontend) + `127.0.0.1:3301` (backend API)
- **Public hostnames** (Caddy, managed outside this repo): `employed.xibodev.com`, `mx.employed.xibodev.com`, `mz.employed.xibodev.com` → :3300; `api.employed.xibodev.com` → :3301. These are the current UAT values of `NEXT_PUBLIC_APP_URL` / `FRONTEND_BASE_URL` / `NEXT_PUBLIC_API_URL` — the domain is env-derived, never hardcoded (AI-OPS Rule 2).
- **On-box compose**: `/opt/employed/docker-compose.yml` (SCPd from `deploy/docker-compose.prod.yml` on every deploy)

## How deployed

- **CI workflow**: `Deploy UAT` → `.github/workflows/deploy-uat.yml` (self-contained; uses `appleboy/ssh-action` + `scp-action` directly — no shared reusable workflow)
- **Images**: `ghcr.io/mekjr1/employed-api:uat`, `ghcr.io/mekjr1/employed-frontend:uat` (floating tags; SHA pinning is an open hardening TODO)
- **Deploy chain**: build+push both images → SSH to Box 3 → copy compose → upsert `/opt/employed/.env` from GitHub secrets → `docker compose pull && docker compose up -d --remove-orphans` → smoke `curl http://localhost:3301/health` (10 × 6 s)
- **Migrations**: the compose `migrate` service runs `alembic upgrade head` before backend/worker start; the workflow itself has no separate migration step
- Deploy is **not** gated on `ci.yml`; pushes to `uat` deploy immediately (hardening TODOs in `.github/copilot-instructions.md`)

## Required secrets (GitHub Actions, names only)

`BOX3_HOST`, `BOX3_SSH_KEY`, `EMPLOYED_UAT_DB_PASSWORD`, `EMPLOYED_UAT_SECRET_KEY`,
`EMPLOYED_UAT_IP_SALT`, `EMPLOYED_UAT_STRIPE_SK`, `EMPLOYED_UAT_STRIPE_WH_SECRET`,
`EMPLOYED_UAT_STRIPE_PK`, `EMPLOYED_UAT_RECAPTCHA_SITE_KEY`,
`EMPLOYED_UAT_RECAPTCHA_SECRET_KEY`, `EMPLOYED_UAT_GOOGLE_CLIENT_ID`,
`EMPLOYED_UAT_GOOGLE_CLIENT_SECRET`, `EMPLOYED_UAT_RESEND_API_KEY`.

Resolve values per `_integrations/CREDENTIALS.md` — never paste them anywhere.

## Required env vars

- Schema reference: `deploy/.env.example` (names + dev placeholders) and `docs/architecture/CONFIG_AND_SECRETS_MAP.md` (var × consumer map). A local `.env.uat.example` mirror exists at the repo root but is gitignored.
- **Known gap (pre-deploy gate for the fix branch)**: `deploy-uat.yml` does not yet upsert `FRONTEND_BASE_URL`, `NEXT_PUBLIC_APP_URL`, `CORS_ORIGINS`, `ENVIRONMENT`, `SENTRY_DSN`, `SENTRY_ENVIRONMENT`. Deploying `fix/quality-run-2026-06-10` without adding them re-breaks the email funnel, credentialed cookie auth, and env-derived domains. See `docs/architecture/DEPLOYMENT_TOPOLOGY.md` § "Deploy-time env gaps".

## Restart procedure

```bash
ssh -i ~/.ssh/contabo_box3 ubuntu@109.123.241.71
cd /opt/employed
docker compose restart
docker compose logs --tail 50
```

## Rollback procedure

Image tags currently float on `:uat` (no per-SHA tags yet), so rollback is by image digest:

```bash
# On the box:
cd /opt/employed
# edit docker-compose.yml: replace 'image: ghcr.io/mekjr1/employed-api:uat'
# with 'image: ghcr.io/mekjr1/employed-api@sha256:<previous-digest>'
docker compose up -d --force-recreate
```

For a code rollback, revert on the `uat` branch and push (triggers a fresh deploy).

## External integrations (actual, this product)

- **Email**: Resend SMTP relay (`smtp.resend.com:465`, SSL; `SMTP_PASSWORD` = Resend API key). Sender `noreply@xibodev.com` until an Employed domain is verified in Resend.
- **Uptime**: UptimeRobot — frontend + API `/health` monitors LIVE (see `docs/operations/uptime-robot.md`).
- **Errors**: Sentry SDKs wired in both backend (`init_sentry()`) and frontend (`@sentry/nextjs`); **no Sentry project/DSN provisioned yet** — no-op until `SENTRY_DSN` is set (operator TODO EMP-011).
- **DNS / TLS**: Cloudflare zone `xibodev.com` + Caddy ACME on Box 3.
- Not used: Vercel, New Relic (not installed), MinIO/S3.

## Drift & notes

- Deploy workflow SCPs the compose file, so source-repo compose edits flow through on the next deploy. The worker's Redis-ping healthcheck fix is committed in `deploy/docker-compose.prod.yml` but the live box still shows the worker false-negative "unhealthy" until the next deploy.
- Live UAT runs pre-fix code (`00aa899`): known live bugs (admin reports 500, API-host email links, broken anonymous-post reCAPTCHA, X-Forwarded-Host market resolution) are fixed on the unmerged branch — see `docs/product/RELEASE_NOTES.md`.

## See also

- `docs/architecture/DEPLOYMENT_TOPOLOGY.md` — full observed topology
- `SERVICES.md` (wrapper folder, canonical) / in-repo `SERVICES.md` — live state + TODOs
- `_integrations/BOXES.md` — box × port allocation
- `_integrations/CREDENTIALS.md` — secret × repo × purpose
