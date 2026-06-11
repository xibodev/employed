---
last_verified: 2026-06-11T02:02:49Z
git_ref: fix/quality-run-2026-06-10 (uat baseline 00aa899)
verified_by: doc-drift audit, quality run 2026-06-10_120309
---

# Sentry Setup

> docs/operations/sentry-setup.md — P-018
>
> **Provisioning status:** the SDK wiring below is in place, but **no Sentry
> project or DSN exists yet for Employed** — nothing is reported from any
> environment. Operator TODO (EMP-011): create `employed-api` +
> `employed-frontend` in org `nmtss`, then set `SENTRY_DSN` /
> `SENTRY_ENVIRONMENT` in the deploy env (the deploy workflow does not yet
> upsert them).

---

## Overview

Both the FastAPI backend (`app/observability.py#init_sentry`) and the Next.js
frontend (`@sentry/nextjs` via `sentry.client/server/edge.config.ts`) are
instrumented with Sentry.
When the relevant env vars are not set (e.g. in local development or CI) Sentry
is a complete no-op — no imports fail, no network traffic is generated.

---

## Required environment variables

### Backend (FastAPI)

| Variable | Required | Description |
|----------|----------|-------------|
| `SENTRY_DSN` | Yes (for prod/uat) | DSN from the Sentry project settings |
| `SENTRY_ENVIRONMENT` | No | Defaults to `uat`. Set to `production` in prod. |
| `SENTRY_TRACES_SAMPLE_RATE` | No | Float 0.0–1.0. Defaults to `0.1` (10 %). |

### Frontend (Next.js)

| Variable | Required | Description |
|----------|----------|-------------|
| `SENTRY_DSN` | Yes (server/edge, for prod/uat) | DSN — server side only |
| `NEXT_PUBLIC_SENTRY_DSN` | Yes (browser, for prod/uat) | Same DSN — exposed to browser bundle |
| `SENTRY_ENVIRONMENT` / `NEXT_PUBLIC_SENTRY_ENVIRONMENT` | No | Defaults to `uat` |

> **Note:** `NEXT_PUBLIC_*` vars are embedded in the browser bundle at build time.
> They are safe to expose for a Sentry DSN (it is by design a public identifier).

---

## Provisioning a Sentry project

1. Log in to [sentry.io](https://sentry.io) and create a new project.
2. Choose platform: **Next.js** for the frontend, **FastAPI** for the backend.
   (Or create a single multi-platform project and use the same DSN for both.)
3. Copy the DSN from *Project Settings → Client Keys*.
4. Add the DSN to the deployment environment (see `.env.example`).

---

## Local development

Leave `SENTRY_DSN` unset (or empty). No Sentry traffic will be generated.

---

## Verifying the integration

### Backend

```bash
# With a real DSN configured:
cd backend
SENTRY_DSN=https://xxx@sentry.io/xxx python -c "
import sentry_sdk
from app.observability import init_sentry
init_sentry()
sentry_sdk.capture_message('Test from backend setup check')
print('Sent. Check Sentry project for the event.')
"
```

### Frontend

Add `NEXT_PUBLIC_SENTRY_DSN` to `.env.local` and run `npm run dev`.
Open the browser console; a `Sentry.captureMessage` call in a component
will appear in the Sentry dashboard within seconds.

---

## Source maps (optional)

To upload source maps to Sentry for readable stack traces in production:

1. Install `@sentry/cli`: `npm install --save-dev @sentry/cli`
2. Configure `SENTRY_AUTH_TOKEN` (from Sentry → Settings → Auth Tokens).
3. Add a `sentry.properties` file (see Sentry docs) or configure via env vars.
4. Source maps are uploaded automatically by `@sentry/nextjs` during `npm run build`
   when `SENTRY_AUTH_TOKEN` is present.
