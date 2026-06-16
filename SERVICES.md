<!-- last_verified: 2026-06-15T00:00:00Z | git_ref: fix/quality-run-2026-06-10 (uat baseline 00aa899) | verified_by: self-contained cleanse 2026-06-15 -->

# Employed — `SERVICES.md`

> **Canonical live-state doc for this product.** Self-contained: no external
> copy and no parent-folder dependency. Infrastructure facts and portfolio
> conventions are captured in `docs/operations/INFRASTRUCTURE.md`.

---

# Employed (employed.co.mz)

## What this product is
Multilingual job board for Mozambique and Mexico. Companies post jobs, candidates browse localized listings, and admins moderate listings before they go live.

## Repos
| Surface | Repo | Path in repo |
|---------|------|--------------|
| Product monorepo | [`mekjr1/employed.co.mz`](https://github.com/mekjr1/employed.co.mz) | repo root |
| Backend API | same repo | `backend/` |
| Frontend | same repo | `frontend/` |
| Deployment | same repo | `deploy/` + `.github/workflows/` |

Repo/folder slug `employed.co.mz` is retained. Live infrastructure uses the shorter brand slug `employed` for `/opt/employed/`, GHCR images, and observability resource names.

## Live state — live build still `uat` @ `00aa899` (verified 2026-06-10)

> **2026-06-15 deploy attempt FAILED.** Branch `fix/quality-run-2026-06-10`
> (40 commits) was merged + pushed to `uat` (`e168f8b`) and both Docker images
> built + pushed to GHCR, but the Box 3 deploy (run `27585388941`) failed at
> `docker compose pull` — `ghcr.io/mekjr1/employed-api:uat … error from
> registry: denied`. **Box 3 cannot authenticate to GHCR, so the live build is
> unchanged (`00aa899`) and every "live bug" below is still live.** Fix: re-auth
> Box 3 to GHCR, then re-run the deploy. Tracked in [`TODO.md`](TODO.md).

| Surface | State |
|---------|-------|
| Backend API | 🟢 **LIVE.** `https://api.employed.xibodev.com/health` returns `200` with DB + Redis OK. FastAPI container on Box 3 via Caddy. |
| Frontend | 🟢 **LIVE.** `https://employed.xibodev.com/` is a self-hosted Next.js container on Box 3. No Vercel project exists for Employed. |
| Market hosts | 🟢 **LIVE** (with caveat). `mx.employed.xibodev.com` and `mz.employed.xibodev.com` reverse-proxy to the same frontend. **Live bug:** the deployed backend ignores `X-Forwarded-Host`, so the MX host serves MZ data (EMP-001 — fixed on the pending branch). |
| Brand domain `employed.co.mz` | 🔴 **NOT ROUTED.** Public DNS is NXDOMAIN; no Cloudflare zone found. Treat as future/prod-domain workstream until ownership/delegation is resolved. |
| PostgreSQL | 🟢 **LIVE.** `postgres:16-alpine` in the Box 3 compose stack with `postgres_data` volume. |
| Redis | 🟢 **LIVE.** `redis:7-alpine` in the Box 3 compose stack; used today for the arq queue and refresh-JTI revocation (no session store — auth is JWT). The pending branch additionally moves rate-limit/lockout counters and webhook replay dedupe into Redis. |
| Worker | 🟠 **FALSE-NEGATIVE UNHEALTHY (live box).** arq jobs run, but the deployed container still uses the inherited HTTP healthcheck. The Redis-ping healthcheck fix is already committed in `deploy/docker-compose.prod.yml` — takes effect on the next deploy. |
| Email | 🟡 **WORKING VIA APEX, BROKEN LINKS.** Resend SMTP via verified `xibodev.com` delivers, but the deployed build's verification/reset links target the API host and 405 on click (EMP-004 — fixed on the pending branch, which links via `FRONTEND_BASE_URL`). |
| Anonymous job posting | 🔴 **BROKEN on live.** reCAPTCHA secret resolution + action mismatch make anonymous posting always fail (EMP-002/003 — fixed on the pending branch). |
| Admin moderation | 🔴 **BROKEN on live when reports exist.** `GET /admin/reports` 500s and blanks the admin UI (EMP-026 — fixed on the pending branch). |
| Error tracking | 🟡 **WIRED, NOT PROVISIONED.** Backend `init_sentry()` and frontend `@sentry/nextjs` configs ship in the deployed build (no-op without DSN). No DSN exists yet. **Target = Bugsink on Box 0** (`errors.xibodev.com`), projects `employed-api` / `employed-web` — a DSN-only swap (EMP-011). See `docs/operations/bugsink-setup.md`. |
| Uptime | 🟢 **LIVE (UptimeRobot, legacy).** Frontend monitor `employed.xibodev.com` (id `803170467`) UP; API monitor `employed-api-uat` (id `803177488`, `/health`) UP. **Portfolio standard is now Gatus on Box 0** — migration pending. See `docs/operations/uptime-monitoring.md`. |

### Pending release — branch `fix/quality-run-2026-06-10` (merged to `uat`, deploy FAILED)

Now **merged + pushed to `uat` (`e168f8b`, 2026-06-15)** — 34 fix commits + the
2026-06-15 self-contained docs cleanse. Both images built + pushed to GHCR, but
the Box 3 deploy (run `27585388941`) **failed at `docker compose pull` (GHCR
`denied`)**, so the live box still runs pre-fix `uat` @ `00aa899`. Branch
behavior is therefore **not yet live** (until Box 3 re-auths to GHCR and the
deploy is re-run): httpOnly `employed_refresh_token` cookie (refresh out of localStorage),
Redis-backed rate limit/lockout, X-Forwarded-Host market resolution,
frontend-targeted email links, working anonymous-post reCAPTCHA, admin
reports fix, runtime `window.__ENV` config, mandatory mobile-money webhook
timestamps. Pre-deploy gate BL-001/BL-002: **resolved on branch 2026-06-11** —
the `deploy-uat.yml` env upsert now sets `FRONTEND_BASE_URL`,
`NEXT_PUBLIC_APP_URL`, exact-origin `CORS_ORIGINS`, `ENVIRONMENT=uat`,
`SENTRY_DSN`, `SENTRY_ENVIRONMENT=uat`; applies on the first post-merge
deploy. Full detail: `docs/product/RELEASE_NOTES.md`.

---

## Hosting & services

### Backend (Box 3)
| | |
|---|---|
| Host | Box 3 (Contabo VPS) — `ubuntu@$BOX3_HOST` (IP in local SSH config / GH secret `BOX3_HOST`, never in-repo) |
| Compose dir | `/opt/employed/` |
| Compose file | `deploy/docker-compose.prod.yml` copied to `/opt/employed/docker-compose.yml` |
| Image | `ghcr.io/mekjr1/employed-api:uat` |
| Port | `3301` host → `8000` container |
| Reverse proxy | Caddy → `api.employed.xibodev.com { reverse_proxy localhost:3301 }` |
| Health | `GET /health` → `{ "status": "ok", "db": "ok", "redis": "ok" }` |
| Stack | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, arq |

### Frontend (Box 3)
| | |
|---|---|
| Image | `ghcr.io/mekjr1/employed-frontend:uat` |
| Port | `3300` host → `3000` container |
| Reverse proxy | Caddy → `employed.xibodev.com`, `mx.employed.xibodev.com`, `mz.employed.xibodev.com` all proxy to `localhost:3300` |
| Stack | Next.js 15, React 19, TypeScript 5.7.2, Tailwind CSS 4 |
| Vercel | Not used; remove Employed from Vercel smoke/CNAME plans. |

### Market host behaviour
| Host | Market | Default locale | Notes |
|------|--------|----------------|-------|
| `employed.xibodev.com` | MZ fallback | `pt` | Default UAT frontend. |
| `mz.employed.xibodev.com` | Mozambique | `pt` | M-Pesa, e-Mola, Stripe provider options. |
| `mx.employed.xibodev.com` | Mexico | `es` | Stripe provider option. |

### Data
| Service | State | Where |
|---------|-------|-------|
| PostgreSQL | self-hosted in compose | Box 3 `/opt/employed/`, volume `postgres_data` |
| Redis | self-hosted in compose | Box 3 compose stack; no separate managed Redis |
| MongoDB | not runtime data store | Historical migration utilities only; shared Meteor/Mongo docs are stale |

---

## External APIs

### Email — Resend SMTP
| | |
|---|---|
| Current verified sender | `Employed <noreply@xibodev.com>` |
| Current relay | `smtp.resend.com:465`, SSL, username `resend` |
| Env | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_USE_SSL`, `FROM_EMAIL` |
| Current reality | Resend apex `xibodev.com` delivers; no Employed-specific sender domain verified yet |
| Target | **AWS SES** (`eu-west-1`) is the portfolio email standard. Verify `employed.xibodev.com` on SES (DKIM), then switch `FROM_EMAIL` to `noreply@employed.xibodev.com`; until verified, fall back to the apex `noreply@xibodev.com` (Resend). Defer an `employed.co.mz` sender until `.mz` DNS exists. See `docs/operations/INFRASTRUCTURE.md`. |

### Authentication
| | |
|---|---|
| Primary auth | Full email/password accounts: register + email verification, login, forgot/reset password. JWT bearer access tokens (30 min) + refresh tokens (7 days). |
| Live (deployed `00aa899`) | Refresh token returned in the response body and persisted by the frontend in localStorage; login lockout is in-process per container; refresh-JTI revocation in Redis. **Live bug:** verification/reset email links target the API host → 405 on click (EMP-004). |
| Pending on branch `fix/quality-run-2026-06-10` (unmerged) | httpOnly `employed_refresh_token` cookie scoped to `/auth` (SameSite=Lax, Secure outside dev); frontend no longer persists refresh tokens in localStorage; (email, client IP) lockout moved to Redis; email links built from `FRONTEND_BASE_URL`; OAuth email-linking requires the provider's verified-email claim (EMP-018). |
| OAuth providers live | Google only (`https://api.employed.xibodev.com/auth/oauth/google/callback`) |
| OAuth env | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` |
| Current credential note | Product docs mention GCP project `employed-uat-1779918377033` |
| Target | Move OAuth/reCAPTCHA clients into the shared `xibodev.com` GCP project per portfolio standard |

Facebook, GitHub, and Twitter OAuth env slots exist in examples, but those providers are not configured and UI buttons are removed for now.

### Payments
| Provider | Market | State | Env |
|----------|--------|-------|-----|
| Stripe | MX + MZ | Test keys configured; webhook endpoint is `POST /webhooks/_stripe/webhook` (router mounted under `/webhooks` — the bare `/_stripe/webhook` path 404s; verify the Stripe dashboard endpoint URL matches) | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PUBLISHABLE_KEY` |
| M-Pesa | MZ | Simulator mode (`MPESA_SIMULATOR`, default true); live adapter not implemented. Callback `POST /webhooks/_mpesa/callback`; pending branch makes the payload timestamp mandatory | `MPESA_SIMULATOR`, `MPESA_WEBHOOK_SECRET` |
| e-Mola | MZ | Simulator mode (`EMOLA_SIMULATOR`, default true); live adapter not implemented. Callback `POST /webhooks/_emola/callback` | `EMOLA_SIMULATOR`, `EMOLA_WEBHOOK_SECRET` |

### reCAPTCHA v3
| | |
|---|---|
| Purpose | Anonymous job-submission abuse protection (action `submit_job`, min score `RECAPTCHA_MIN_SCORE`) |
| Env | `RECAPTCHA_SECRET_KEY`, `NEXT_PUBLIC_RECAPTCHA_SITE_KEY`, `RECAPTCHA_MIN_SCORE`, `RECAPTCHA_BYPASS_IN_DEVELOPMENT` |
| Current state | UAT keys present in GitHub secrets. **Live build broken** for anonymous posting (secret resolution + action mismatch, EMP-002/003 — fixed on the pending branch). Live frontend bakes the site key at build time; the pending branch serves it at runtime via `window.__ENV`. |

---

## Observability

| Channel | Project / config |
|---------|------------------|
| Error tracking (Bugsink) | **Target = Bugsink on Box 0** (`https://errors.xibodev.com`), projects `employed-api` + `employed-web`, team `xibodev`. **SDKs wired both ends** (backend `init_sentry()`; frontend `@sentry/nextjs` client/server/edge configs) — no-op until DSN set. **DSN not provisioned yet** (EMP-011 operator TODO). Bugsink is Sentry-SDK compatible, so this is a DSN-only swap; the legacy Sentry SaaS org stays read-only. See `docs/operations/bugsink-setup.md`. |
| New Relic | app name pattern `employed-api-uat`, `employed-frontend-uat`, optionally `employed-worker-uat`. **Agent not installed yet.** |
| Uptime | 🟢 LIVE on **UptimeRobot (legacy)** — frontend monitor `employed.xibodev.com` (id `803170467`) and API monitor `employed-api-uat` (id `803177488`, `/health`), 5-min interval. Portfolio standard is now **Gatus on Box 0** (migration pending). See `docs/operations/uptime-monitoring.md`. |
| Loki / Grafana / Promtail | **NOT USED.** Retired with Box A. |
| Health endpoints | API `/health` (GET + HEAD); frontend `/api/health`. No `/healthz` or `/metrics` endpoints exist. |

---

## CI/CD

### Backend + frontend UAT deploy
| | |
|---|---|
| Workflow | `.github/workflows/deploy-uat.yml` |
| Trigger | push to `uat` branch, ignoring docs-only paths |
| Build | Docker build/push to `ghcr.io/mekjr1/employed-api:uat` and `ghcr.io/mekjr1/employed-frontend:uat` |
| Deploy | SSH to Box 3 as `ubuntu`; ensure `/opt/employed/`; copy compose; upsert `.env`; `docker compose pull && docker compose up -d --remove-orphans` |
| Smoke | `curl -fsSo /dev/null http://localhost:3301/health` |
| GH secrets | `BOX3_HOST`, `BOX3_SSH_KEY`, `EMPLOYED_UAT_DB_PASSWORD`, `EMPLOYED_UAT_SECRET_KEY`, `EMPLOYED_UAT_IP_SALT`, Stripe, reCAPTCHA, Google, Resend secrets |
| Recent evidence | Latest audited deploy run `26541953900` succeeded on `uat` (2026-05-27). |

### CI
| | |
|---|---|
| Workflow | `.github/workflows/ci.yml` |
| Trigger | push to `main`/`master`/`uat`, all pull requests |
| Jobs | backend Ruff lint/format, backend pytest, frontend ESLint/TypeScript, frontend build |
| Branch note | GitHub default branch is still `master` (rename to `main` pending); deploy branch is `uat`. Deploy is not gated on CI (hardening TODO). |

### One-time init
| | |
|---|---|
| Workflow | `.github/workflows/init-server.yml` |
| Trigger | manual `workflow_dispatch` |
| Purpose | creates `/opt/employed/`, fixes ownership, creates chmod-600 `.env` |

---

## Env conventions (this product)

| Var | Value | Notes |
|-----|-------|-------|
| `APP_NAME` | `Employed API` | Default in `backend/app/config.py` already matches brand. |
| `DATABASE_URL` | `postgresql://employed:<secret>@postgres:5432/employed` | In-compose Postgres on Box 3. |
| `REDIS_URL` | `redis://redis:6379/0` | In-compose Redis on Box 3. |
| `NEXT_PUBLIC_API_URL` | `https://api.employed.xibodev.com` | Live build: baked at image build. Pending branch: served at runtime via `window.__ENV` (build-arg only a fallback). |
| `FRONTEND_BASE_URL` / `NEXT_PUBLIC_APP_URL` / `CORS_ORIGINS` / `ENVIRONMENT` | not yet set on Box 3 (upsert added on branch) | BL-001 resolved on branch 2026-06-11: `deploy-uat.yml` upserts all four (+ `SENTRY_*`); lands on Box 3 with the first post-merge deploy. |
| `FROM_EMAIL` | `Employed <noreply@xibodev.com>` now | Switch to `noreply@employed.xibodev.com` after SES DKIM verification (`eu-west-1`). |
| `ADMIN_EMAIL` | `admin@employed.co.mz` | Current deploy value; verify mailbox/domain before relying on it. |
| `SMTP_*` | Resend SMTP relay | UAT uses port `465` + SSL. |
| `GOOGLE_CLIENT_ID/SECRET` | present in GH secrets | Google-only OAuth for now. |
| `RECAPTCHA_*` | present in GH secrets | Live: site key build-time; pending branch: runtime via `window.__ENV`. |
| `STRIPE_*` | test keys | Live keys required before real payments. |
| `MPESA_WEBHOOK_SECRET` / `EMOLA_WEBHOOK_SECRET` | absent/pending | Absence means simulator mode. |
| `SENTRY_DSN` / `SENTRY_ENVIRONMENT` | pending | Add after projects/SDKs are provisioned. |
| `NEW_RELIC_APP_NAME` | `employed-api-uat` / `employed-frontend-uat` | Use when NR agent is installed. |

---

## TODO — critical path to make UAT release-gated

0. ~~**NEW (hard pre-deploy gate, BL-001/BL-002):** extend the `deploy-uat.yml` env upsert with `FRONTEND_BASE_URL`, `NEXT_PUBLIC_APP_URL`, `CORS_ORIGINS`, `ENVIRONMENT`, `SENTRY_DSN`, `SENTRY_ENVIRONMENT`.~~ **DONE in repo 2026-06-11** — upsert block extended on the fix branch; takes effect on the first post-merge deploy (live box unchanged until then).
1. ~~**Fix worker health status.**~~ **DONE in repo** — Redis-ping healthcheck committed in `deploy/docker-compose.prod.yml`; takes effect on the next deploy (live box still shows the false-negative until then).
2. ~~**Create uptime monitors.**~~ **DONE 2026-05-29** (UptimeRobot `803170467` + `803177488`). **Follow-up:** migrate to the portfolio standard, **Gatus on Box 0**, then retire the UptimeRobot monitors. See `docs/operations/uptime-monitoring.md`.
3. **Provision Bugsink**: create `employed-api` + `employed-web` projects in **Bugsink** (`errors.xibodev.com`, Box 0, team `xibodev`) and set `SENTRY_DSN` + `SENTRY_ENVIRONMENT=uat` in the deploy env. Bugsink is Sentry-SDK compatible, so the wired SDKs (backend `init_sentry()`, frontend `@sentry/nextjs`) need only the DSN. See `docs/operations/bugsink-setup.md`.
4. **Install/configure New Relic** for API/frontend (and worker if supported); use brand/env app names above.
5. **Verify `employed.xibodev.com` on AWS SES** (`eu-west-1`, portfolio email standard) and switch `FROM_EMAIL` to `noreply@employed.xibodev.com` after DKIM verification. Until then, keep the apex `noreply@xibodev.com` (Resend) or mail bounces.
6. **Resolve `.mz` domain ownership/delegation** before adding production-domain DNS or Caddy routes.
7. **Align branch policy**: keep `uat` deploy branch, then rename `master` → `main` (CI already covers `master` and `uat`).
8. **Confirm M-Pesa and e-Mola sandbox credentials** before mobile-money UAT journeys that claim real provider coverage. (Pending branch makes the callback timestamp mandatory — confirm providers send one.)

## TODO — cleanup (post-restore)

- Replace old shared-doc claims that Employed is Meteor/Mongo/Node 18 or Vercel-hosted; current stack is FastAPI + Next.js + PostgreSQL/Redis on Box 3. *(In-repo docs swept 2026-06-10 — remaining instances live only in central/shared docs.)*
- ~~Update `deploy/.env.example` sender from `Employed <admin@employed.co.mz>` to the safe UAT sender.~~ **DONE 2026-06-10** (now `Employed <noreply@xibodev.com>`).
- ~~Update `docs/operations/oncall.md`: UptimeRobot should target `/health`; remove `/healthz?db=1` and `/metrics` unless implemented.~~ **DONE 2026-05-28** (HEAD/405 fix + doc sync).
- ~~Update `PITCH.md` references to Box A and already-wired Sentry.~~ **DONE 2026-06-10** (Box A removed; Sentry stated as wired-not-provisioned; test counts corrected).
- Update GitHub repo description from the old Meteor job-board wording. *(Verified still stale 2026-06-10: "A Meteor based Job Board".)*
- Move current Google OAuth/reCAPTCHA credentials into the shared `xibodev.com` GCP project when rotating credentials.
- ~~Keep historical Meteor migration docs clearly archived/reference-only.~~ **DONE 2026-06-10** (banners on `docs/meteor-3-package-audit.md`, `docs/ads-strategy.md`, ADRs 001–004 marked Superseded, CHANGELOG Meteor era fenced off).

## TODO — backlog

- Activate `employed.co.mz` as a production/custom domain after registration/delegation is confirmed.
- Add production host plan for `api.employed.co.mz`, `mx.employed.co.mz`, and `mz.employed.co.mz` only after `.mz` DNS is approved.
- Decide later whether to migrate Postgres/Redis from product compose to Box 1 shared services; do not move the live UAT database without a migration window.
- Replace mobile-money simulator mode with real M-Pesa/e-Mola sandbox integrations.
- Consider CDN/edge caching for the self-hosted Next.js frontend once traffic justifies it.

---

## Cross-links (all in-repo — this repo is self-contained)

- Infrastructure, port block, domains, box, error/email/uptime standards, secrets boundary: `docs/operations/INFRASTRUCTURE.md`
- Deployment procedure + rollback: `DEPLOY.md`
- Full observed architecture: `docs/architecture/`
- Error tracking setup: `docs/operations/bugsink-setup.md`
- Uptime monitoring: `docs/operations/uptime-monitoring.md`
