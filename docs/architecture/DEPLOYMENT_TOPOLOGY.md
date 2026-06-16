---
last_verified: 2026-06-14T00:00:00Z
git_ref: working-tree (fix/quality-run-2026-06-10 lineage; uat baseline 00aa899)
verified_by: codebase-cartographer — FP-CARTO-007 doc refresh (2026-06-14)
---

# Deployment Topology — Employed

Sources: `deploy/docker-compose*.yml`, `backend/Dockerfile`,
`frontend/Dockerfile`, `.github/workflows/{ci,deploy-uat,init-server}.yml`,
`DEPLOY.md`; live UAT facts cross-checked against the wrapper-level
`SERVICES.md` (2026-05-28 snapshot). This doc describes the topology **as
defined on this branch** — the branch is not yet deployed.

## Environments

| Env | Where | Compose file | Status |
|-----|-------|--------------|--------|
| Local dev | dev machine | `deploy/docker-compose.yml` (+ `docker-compose.dev.yml` overlay: live-reload mounts, PG on 3302, Redis on 3303) | builds from source |
| Local test/UAT-mirror | dev machine | base + `docker-compose.test.yml` overlay (adds MailHog 3310 UI / 3311 SMTP, exposes PG/Redis) | used by quality runs |
| UAT | Box 3 (Contabo VPS), `/opt/employed/` | `deploy/docker-compose.prod.yml` copied to `/opt/employed/docker-compose.yml` | LIVE (uat branch images) |
| Production | — | — | does not exist yet; `.mz` brand domain unrouted |

Local host-port block (Box 3 allocation, governs local/UAT; see
`docs/operations/INFRASTRUCTURE.md`): frontend **3300**, backend **3301**,
postgres 3302, redis 3303, MailHog 3310/3311.

## Compose service graph (prod file, identical shape locally)

```
migrate (alembic upgrade head, runs to completion)
  ▲ depends_on: postgres healthy
backend (uvicorn :8000) ── host 127.0.0.1:3301
  ▲ depends_on: postgres healthy, redis healthy, migrate completed
worker (arq WorkerSettings) — no ports
  ▲ depends_on: same as backend
frontend (node server.js :3000) ── host 127.0.0.1:3300
  ▲ depends_on: backend healthy
postgres:16-alpine ── volume postgres_data
redis:7-alpine ── no persistence (--save "" --appendonly no)
```

Healthchecks (as defined in `deploy/docker-compose.prod.yml` on this branch):

| Service | Check |
|---------|-------|
| backend | HTTP GET `http://127.0.0.1:8000/health` in-container |
| worker | **Redis ping** (`redis.Redis.from_url(REDIS_URL).ping()`) — replaces the inherited HTTP check that caused the long-standing false-negative "unhealthy" worker; takes effect on next deploy |
| frontend | `wget http://127.0.0.1:3000/api/health` |
| postgres / redis | `pg_isready` / `redis-cli ping` |

Both published ports bind to **127.0.0.1 only**; the only ingress is Caddy.

## UAT ingress (Box 3 Caddy — managed outside this repo)

| Host | Proxies to | Notes |
|------|-----------|-------|
| `employed.xibodev.com` | localhost:3300 | apex → MZ default market, locale pt |
| `mz.employed.xibodev.com` | localhost:3300 | MZ market |
| `mx.employed.xibodev.com` | localhost:3300 | MX market, locale es |
| `api.employed.xibodev.com` | localhost:3301 | FastAPI |

Market selection happens **after** the proxy: the frontend sends
`X-Forwarded-Host` with the browser host on every API call, and the backend's
`MarketMiddleware` resolves the market from it (EMP-001). The repo also ships
a reference `deploy/nginx.conf` (for the future `mz./mx.employed.co.mz`
production hosts) — not used on Box 3, where Caddy fills that role.

## Images

| Image | Built from | Registry tag |
|-------|-----------|--------------|
| API/worker/migrate | `backend/Dockerfile` — 2-stage python:3.12-slim; venv with the three pinned runtime requirement sets only (EMP-021); uvicorn :8000 | `ghcr.io/mekjr1/employed-api:uat` |
| frontend | `frontend/Dockerfile` — 3-stage node:20-alpine; `next build` standalone; `NEXT_PUBLIC_API_URL`/`NEXT_PUBLIC_RECAPTCHA_SITE_KEY` build args kept only as fallbacks — runtime env wins via `window.__ENV` (EMP-012) | `ghcr.io/mekjr1/employed-frontend:uat` |

No image pinning by SHA yet — both tags float on `:uat` (hardening TODO in
`SERVICES.md`).

## CI/CD pipelines (`.github/workflows/`)

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| `ci.yml` | push to main/master/uat, all PRs | backend Ruff (check+format) and pytest against PG16+Redis7 service containers; frontend ESLint + tsc + `next build` |
| `deploy-uat.yml` | push to `uat` (ignores `**.md`, `docs/**`) | build+push both images to GHCR → SSH to Box 3 → copy `docker-compose.prod.yml` → upsert `/opt/employed/.env` from GitHub secrets → `docker compose pull && up -d --remove-orphans` → smoke `curl http://localhost:3301/health` (10×6 s) |
| `init-server.yml` | manual | one-time `/opt/employed/` creation + chmod-600 `.env` |

Deploy is **not** gated on `ci.yml`, runs no `alembic upgrade` step itself
(the compose `migrate` service covers it at container start), and merging a
PR to `uat` deploys immediately. Branch state: GitHub default branch is
still `master`; deploy branch is `uat`.

GitHub secrets consumed by deploy (names only): `BOX3_HOST`, `BOX3_SSH_KEY`,
`EMPLOYED_UAT_DB_PASSWORD`, `EMPLOYED_UAT_SECRET_KEY`, `EMPLOYED_UAT_IP_SALT`,
`EMPLOYED_UAT_STRIPE_SK/_WH_SECRET/_PK`,
`EMPLOYED_UAT_RECAPTCHA_SITE_KEY/_SECRET_KEY`,
`EMPLOYED_UAT_GOOGLE_CLIENT_ID/_SECRET`, `EMPLOYED_UAT_RESEND_API_KEY`
(current email relay; target is SES SMTP creds once `employed.xibodev.com` is
SES-verified — planned), plus optional `EMPLOYED_UAT_SENTRY_DSN` (absent →
empty → Sentry no-op; the target value when set is a **Bugsink DSN on Box 0**,
not a Sentry SaaS DSN — planned, pending provisioning).

## Deploy-time env gaps (observed against this branch's code)

**Resolved on branch, pending merge (BL-001 / CARTO-002, 2026-06-11).** The
`deploy-uat.yml` env-upsert block now sets the variables this branch's code
reads at runtime:

- `FRONTEND_BASE_URL=https://employed.xibodev.com` — email verify/reset links
  (EMP-004).
- `NEXT_PUBLIC_APP_URL=https://employed.xibodev.com` — market-host/robots/
  sitemap derivation (EMP-013/024).
- `CORS_ORIGINS` — exact UAT origins (`employed`, `mx.employed`,
  `mz.employed` on `.xibodev.com`) for credentialed cookie refresh (EMP-006).
- `ENVIRONMENT=uat` — HSTS/secure-cookie/dev-default gating.
- `SENTRY_DSN` (optional `EMPLOYED_UAT_SENTRY_DSN` secret; empty-safe) /
  `SENTRY_ENVIRONMENT=uat` — live once Sentry is provisioned (EMP-011/BL-003).

Deliberately not upserted: `TRUSTED_PROXY_IPS` (loopback/RFC1918 default is
correct for Box 3's Caddy-on-localhost). The new values land on Box 3 with the
first post-merge deploy run.

## Backups / persistence

- Postgres: named volume `postgres_data`; `backend/scripts/backup-db.sh` +
  `docs/operations/postgres-backup.md` describe the dump procedure.
- Redis: deliberately ephemeral (queue/limits/revocation only) — restart
  clears rate-limit counters, lockouts, revoked JTIs and replay-dedupe keys;
  all are TTL-bounded by design.

## Cross-box / external dependencies (planned)

Beyond Box 3's in-compose Postgres/Redis, two portfolio-standard external
dependencies are **planned/target state** — not yet wired into this repo or
the Box 3 deploy. They are config-level, not topology rewrites:

| Dependency | Where | Role | Status |
|------------|-------|------|--------|
| **Bugsink** (error tracking) | **Box 0** — `https://errors.xibodev.com`, stack `xibodev-atlas/box0/` | Sentry-SDK-compatible error sink; Box 3 backend/worker/frontend would emit to a Bugsink DSN (projects `employed-api`, `employed-web`/`employed-uat`, team `xibodev`). Portfolio standard since 2026-06-11. | **planned — pending DSN provisioning**; SDK already wired, DSN-only change. Source: `docs/operations/INFRASTRUCTURE.md` (Error tracking) |
| **AWS SES** (transactional email) | AWS **eu-west-1** (default region) | Outbound SMTP relay for verification/reset/job-lifecycle mail, replacing Resend. Config-level swap (SMTP creds + sender domain). Target sender `noreply@employed.xibodev.com` after DKIM verification; fall back to `noreply@xibodev.com` (Resend apex) until verified. Employed is on the priority SES bulk-verify list. | **planned — pending SES domain verification.** Source: `docs/operations/INFRASTRUCTURE.md` (Email — transactional) |

These do not change the Box 3 compose graph or Caddy ingress; they alter only
the `SENTRY_DSN` and SMTP/sender env values (see CONFIG_AND_SECRETS_MAP.md).

## Monitoring (live UAT)

- UptimeRobot: frontend monitor (`employed.xibodev.com`) and API monitor
  (`https://api.employed.xibodev.com/health`), 5-min interval — both UP per
  `SERVICES.md` / `docs/operations/uptime-monitoring.md`. (Portfolio uptime standard
  has moved to **Gatus on Box 0** since 2026-06-10; not yet wired here.)
- Error tracking: Sentry SDK wired both ends but **no DSN set** (dormant). The
  target is a **Bugsink DSN on Box 0** (see Cross-box dependencies above) —
  planned, pending DSN provisioning. Do not stand up a new Sentry SaaS project.
- New Relic (APM): not provisioned yet (portfolio-wide TODO).
