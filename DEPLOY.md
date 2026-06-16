---
last_verified: 2026-06-15T00:00:00Z
git_ref: fix/quality-run-2026-06-10 (uat baseline 00aa899)
verified_by: self-contained cleanse 2026-06-15
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
| Live UAT baseline | live build `uat` @ `00aa899`; `uat` branch ref now `e168f8b` (merged 2026-06-15). Deploy run `27585388941` **FAILED** at `docker compose pull` (GHCR `denied` on Box 3) — live build unchanged. See Drift & notes |

## Where deployed

- **Box**: Box 3 (Contabo VPS) — host/IP in local SSH config + GH secret `BOX3_HOST` (never in-repo)
- **Host ports (loopback only)**: `127.0.0.1:3300` (frontend) + `127.0.0.1:3301` (backend API)
- **Public hostnames** (Caddy, managed outside this repo): `employed.xibodev.com`, `mx.employed.xibodev.com`, `mz.employed.xibodev.com` → :3300; `api.employed.xibodev.com` → :3301. These are the current UAT values of `NEXT_PUBLIC_APP_URL` / `FRONTEND_BASE_URL` / `NEXT_PUBLIC_API_URL` — the domain is env-derived, never hardcoded.
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

Optional: `EMPLOYED_UAT_SENTRY_DSN` (absent → empty string → backend Sentry
no-op; provision per BL-003 and the workflow picks it up on the next deploy).

Values live only in GitHub Actions secrets and the operator vault — never paste them anywhere or commit them. See `docs/operations/INFRASTRUCTURE.md` § Secrets boundary.

## Required env vars

- Schema reference: `deploy/.env.example` (names + dev placeholders) and `docs/architecture/CONFIG_AND_SECRETS_MAP.md` (var × consumer map). A local `.env.uat.example` mirror exists at the repo root but is gitignored.
- **Pre-deploy gate BL-001 — resolved on branch, pending merge (2026-06-11)**: the `deploy-uat.yml` env upsert now sets `FRONTEND_BASE_URL`, `NEXT_PUBLIC_APP_URL`, `CORS_ORIGINS` (exact UAT origins), `ENVIRONMENT=uat`, `SENTRY_DSN` (from the optional `EMPLOYED_UAT_SENTRY_DSN` secret), and `SENTRY_ENVIRONMENT=uat`. Takes effect on the first deploy after the branch merges to `uat`. See `docs/architecture/DEPLOYMENT_TOPOLOGY.md` § "Deploy-time env gaps".

## Restart procedure

```bash
ssh -i ~/.ssh/contabo_box3 ubuntu@$BOX3_HOST   # Box 3 IP from local SSH config / GH secret BOX3_HOST
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

- **Email**: Resend SMTP relay (`smtp.resend.com:465`, SSL; `SMTP_PASSWORD` = Resend API key), sender `noreply@xibodev.com`. **Target: AWS SES** (`eu-west-1`) with sender `noreply@employed.xibodev.com` once `employed.xibodev.com` is DKIM-verified — see `docs/operations/INFRASTRUCTURE.md`.
- **Uptime**: UptimeRobot — frontend + API `/health` monitors LIVE (legacy). Portfolio standard is **Gatus on Box 0** (migration pending). See `docs/operations/uptime-monitoring.md`.
- **Errors**: Sentry SDKs wired in both backend (`init_sentry()`) and frontend (`@sentry/nextjs`); **no DSN provisioned yet** — no-op until `SENTRY_DSN` is set. Target is **Bugsink on Box 0** (`errors.xibodev.com`), a DSN-only swap (operator TODO EMP-011). See `docs/operations/bugsink-setup.md`.
- **DNS / TLS**: Cloudflare zone `xibodev.com` + Caddy ACME on Box 3.
- Not used: Vercel, New Relic (not installed), MinIO/S3.

## Drift & notes

- **2026-06-15 deploy FAILED (run `27585388941`).** `uat` was fast-forwarded to `e168f8b` and both images built + pushed to GHCR, but Box 3's `docker compose pull` returned `ghcr.io/mekjr1/employed-api:uat … error from registry: denied` — the box is not authenticated to GHCR (expired token or package read perms). Live build is therefore unchanged (`00aa899`). **Fix:** on Box 3 run `docker login ghcr.io` with a valid token (or make the GHCR packages readable), then re-run the Deploy UAT workflow. Tracked in `TODO.md`.
- Deploy workflow SCPs the compose file, so source-repo compose edits flow through on the next deploy. The worker's Redis-ping healthcheck fix is committed in `deploy/docker-compose.prod.yml` but the live box still shows the worker false-negative "unhealthy" until the next deploy.
- Live UAT runs pre-fix code (`00aa899`): known live bugs (admin reports 500, API-host email links, broken anonymous-post reCAPTCHA, X-Forwarded-Host market resolution) are fixed on the merged-but-undeployed `uat` ref (`e168f8b`) — see `docs/product/RELEASE_NOTES.md`.

## See also

- `docs/architecture/DEPLOYMENT_TOPOLOGY.md` — full observed topology
- `SERVICES.md` — canonical live state + TODOs
- `docs/operations/INFRASTRUCTURE.md` — box, port block, domains, error/email/uptime standards, secrets boundary
