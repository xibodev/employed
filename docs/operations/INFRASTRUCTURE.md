<!-- last_verified: 2026-06-15T00:00:00Z | git_ref: fix/quality-run-2026-06-10 | verified_by: self-contained cleanse 2026-06-15 -->

# Infrastructure & Operating Context — employed.co.mz

> **This repository is self-contained.** Everything needed to understand,
> build, deploy, and operate Employed lives inside this repo. This document
> captures the infrastructure facts and portfolio conventions Employed relies
> on, snapshotted here so no external/parent documentation is required.
>
> **Identity-bearing values are deliberately NOT stored here** — Box IPs,
> account IDs, ARNs, AWS profile names, DSNs, API keys, and tokens live only in
> deploy-time GitHub Actions secrets, the operator's local config (SSH config,
> AWS credentials file), or the password vault. This doc names *what* and
> *where*, never the secret value.

---

## Deployment target

| | |
|---|---|
| Environment | **UAT only.** No production environment exists yet. |
| Box | **Box 3** — Contabo VPS (consumer + SaaS product backends). Host/IP via GitHub secret `BOX3_HOST`; SSH key via `BOX3_SSH_KEY` (operator's local key is `~/.ssh/contabo_box3`). |
| Compose dir | `/opt/employed/` on the box |
| Reverse proxy | Caddy on Box 3 (ACME TLS), managed outside this repo |
| Images | `ghcr.io/xibodev/employed-api:uat`, `ghcr.io/xibodev/employed-frontend:uat` (floating `:uat` tag; SHA-pinning is an open hardening item). |

## Host-port allocation (Box 3 / local)

Employed's assigned host-port block. Only the host side is fixed; container
ports are whatever the upstream app expects. Keep new host ports inside this
block so co-located products on the same box don't clash.

| Port | Service | Container |
|------|---------|-----------|
| `3300` | frontend (Next.js) | `:3000` |
| `3301` | backend API (FastAPI) | `:8000` |
| `3302` | postgres (dev/test only) | `:5432` |
| `3303` | redis (dev/test only) | `:6379` |
| `3310` / `3311` | MailHog UI / SMTP (test only) | `:8025` / `:1025` |

Local defaults outside Docker: frontend `http://localhost:3000`, backend
`http://localhost:8000`.

## Domains

| Surface | UAT host | Notes |
|---------|----------|-------|
| Frontend (apex) | `employed.xibodev.com` | MZ-default market, locale `pt` |
| Frontend (MZ) | `mz.employed.xibodev.com` | Mozambique market |
| Frontend (MX) | `mx.employed.xibodev.com` | Mexico market, locale `es` |
| Backend API | `api.employed.xibodev.com` | FastAPI |

- UAT runs under the umbrella pattern `<slug>.xibodev.com`. Employed's slug is
  `employed` (the repo/folder keeps the longer `employed.co.mz` name).
- **The deployment domain is never hardcoded in source.** It is derived from
  `NEXT_PUBLIC_APP_URL` (frontend market/robots/sitemap), `FRONTEND_BASE_URL`
  (backend email links), and `NEXT_PUBLIC_API_URL` (frontend → API). Changing
  the domain is a config change (restart), not a rebuild.
- The production brand domain `employed.co.mz` is **not routed** (public DNS is
  NXDOMAIN). Treat production-domain work as a future workstream gated on `.mz`
  delegation.

## Error tracking — Bugsink (planned cutover)

- **Standard:** **Bugsink**, self-hosted on **Box 0** at
  `https://errors.xibodev.com`. Bugsink is **Sentry-SDK compatible** — the app
  keeps its existing `sentry_sdk` (backend) / `@sentry/nextjs` (frontend) code
  and only the **DSN** changes.
- **Employed projects:** `employed-api` (backend) and `employed-web` (frontend),
  team `xibodev`.
- **Current state:** SDKs are wired both ends but **no DSN is set** (complete
  no-op). When a DSN is finally provisioned it must be a **Bugsink** DSN — never
  a new Sentry SaaS project.
- **Legacy:** the old Sentry SaaS org is kept read-only for historical events;
  create no new projects there.
- See `docs/operations/bugsink-setup.md`.

## Transactional email — AWS SES (planned cutover)

- **Standard:** **AWS SES** (region `eu-west-1`). SES is the same backend Resend
  wraps, so the move is a credential/sender swap, not a code change.
- **Current state:** Resend SMTP relay (`smtp.resend.com:465`, SSL), sender
  `Employed <noreply@xibodev.com>` via the verified `xibodev.com` apex.
- **Target:** sender `noreply@employed.xibodev.com` once `employed.xibodev.com`
  is DKIM-verified on SES. Until verified, fall back to the apex
  `noreply@xibodev.com` or mail bounces. Employed is on the priority
  domain-verification list.
- Env consumed by the app: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`,
  `SMTP_PASSWORD`, `SMTP_USE_SSL`, `FROM_EMAIL`. (`SMTP_PASSWORD` carries the
  provider API key; there is no separate `RESEND_API_KEY` var in the app env.)

## Uptime monitoring — Gatus (standard) / UptimeRobot (legacy)

- **Standard:** **Gatus** on Box 0 (replaced UptimeRobot as the portfolio
  standard 2026-06-10).
- **Current state:** Employed's live monitors are still on **UptimeRobot**
  (frontend + API `/health`). Migration to Gatus is pending.
- See `docs/operations/uptime-monitoring.md`.

## AWS

- Use the portfolio-default **personal** AWS profile. The literal profile name
  lives in the operator's local `~/.aws/config` — it is **not** committed here.
- Default region for this product's AWS usage (SES) is `eu-west-1`.

## CI/CD

| | |
|---|---|
| CI | `.github/workflows/ci.yml` — backend Ruff + pytest, frontend ESLint + tsc + build. Runs on push to `master`/`uat` and all PRs. |
| Deploy | `.github/workflows/deploy-uat.yml` — push to `uat` builds + pushes both images, SSHes to Box 3, upserts `/opt/employed/.env` from GitHub secrets, `docker compose pull && up -d`, smoke-tests `/health`. |
| Gating | Deploy is **not yet gated on CI** (hardening item — see `.github/copilot-instructions.md`). |
| Default branch | GitHub default is `master`; deploy branch is `uat`. Rename `master → main` is an open TODO. |

Full deploy procedure, rollback, and required-secret names: `DEPLOY.md`.

## Secrets boundary

GitHub Actions holds (names only — values never in-repo): `BOX3_HOST`,
`BOX3_SSH_KEY`, `EMPLOYED_UAT_DB_PASSWORD`, `EMPLOYED_UAT_SECRET_KEY`,
`EMPLOYED_UAT_IP_SALT`, `EMPLOYED_UAT_STRIPE_SK/_WH_SECRET/_PK`,
`EMPLOYED_UAT_RECAPTCHA_SITE_KEY/_SECRET_KEY`,
`EMPLOYED_UAT_GOOGLE_CLIENT_ID/_SECRET`, `EMPLOYED_UAT_RESEND_API_KEY`, and the
optional `EMPLOYED_UAT_SENTRY_DSN` (will carry a Bugsink DSN once provisioned).
Never paste secret values into chat, commits, or docs — reference them by name.

## Conventions

- **Locale codes:** `en`, `pt`, `es` only. No extended tags like `pt-MZ`.
- **Runtime config:** mutable values (host URLs, sender address, feature flags,
  provider `mock`/`live` mode) resolve from env / mounted config at runtime — a
  change to any of them is a **restart, not a rebuild**.
- **No AI-authorship trailers** in commits or docs.
- **No `.env` / secrets in git** — see `deploy/.env.example`,
  `frontend/.env.example`.
