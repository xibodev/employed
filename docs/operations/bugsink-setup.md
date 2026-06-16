<!-- last_verified: 2026-06-15T00:00:00Z | git_ref: fix/quality-run-2026-06-10 | verified_by: self-contained cleanse 2026-06-15 -->

# Error Tracking Setup — Bugsink

> **Standard:** **Bugsink**, self-hosted on **Box 0** at
> `https://errors.xibodev.com`. Bugsink is Sentry-SDK compatible, so the app
> code is unchanged — only the **DSN** points at Bugsink instead of Sentry SaaS.
>
> **Provisioning status:** the SDK wiring below is in place, but **no DSN is set
> for Employed** — nothing is reported from any environment. Operator TODO:
> create the `employed-api` + `employed-web` projects in Bugsink (team
> `xibodev`), then set `SENTRY_DSN` / `SENTRY_ENVIRONMENT` in the deploy env.

---

## Overview

Both the FastAPI backend (`app/observability.py#init_sentry`) and the Next.js
frontend (`@sentry/nextjs` via `sentry.client/server/edge.config.ts`) are
instrumented with the Sentry SDK. Bugsink ingests the same wire protocol, so the
SDKs talk to it directly — only the DSN host differs.

When the relevant env vars are not set (local dev, CI) the SDK is a complete
no-op — no imports fail, no network traffic is generated.

## Required environment variables

The SDK env-var **names are unchanged** from Sentry; only the DSN *value* comes
from Bugsink.

### Backend (FastAPI)

| Variable | Required | Description |
|----------|----------|-------------|
| `SENTRY_DSN` | Yes (uat/prod) | DSN copied from the Bugsink `employed-api` project |
| `SENTRY_ENVIRONMENT` | No | Defaults to `uat`. Set `production` in prod. |
| `SENTRY_TRACES_SAMPLE_RATE` | No | Float 0.0–1.0. Defaults to `0.1` (10%). |

### Frontend (Next.js)

| Variable | Required | Description |
|----------|----------|-------------|
| `SENTRY_DSN` | Yes (server/edge) | Bugsink `employed-web` DSN — server side |
| `NEXT_PUBLIC_SENTRY_DSN` | Yes (browser) | Same DSN — exposed to the browser bundle |
| `SENTRY_ENVIRONMENT` / `NEXT_PUBLIC_SENTRY_ENVIRONMENT` | No | Defaults to `uat` |

> A DSN is a public identifier by design, so `NEXT_PUBLIC_SENTRY_DSN` is safe to
> embed in the browser bundle.

## Provisioning the Bugsink projects

1. Sign in to `https://errors.xibodev.com` (admin credential is in the operator
   vault under "Bugsink (errors.xibodev.com) superuser").
2. In team `xibodev`, create two projects: `employed-api` and `employed-web`.
   (Projects can also be created server-side via `bugsink-manage shell`.)
3. Copy each project's DSN from its settings.
4. Set the DSN in the deploy environment: backend uses the `employed-api` DSN;
   the frontend uses the `employed-web` DSN. The deploy workflow reads it from
   the `EMPLOYED_UAT_SENTRY_DSN` GitHub secret and upserts `SENTRY_DSN` +
   `SENTRY_ENVIRONMENT` into `/opt/employed/.env`.

## Local development

Leave `SENTRY_DSN` unset (or empty). No error traffic is generated.

## Verifying the integration

### Backend

```bash
# With a real Bugsink DSN configured:
cd backend
SENTRY_DSN=https://<key>@errors.xibodev.com/<project> python -c "
import sentry_sdk
from app.observability import init_sentry
init_sentry()
sentry_sdk.capture_message('Test from backend setup check')
print('Sent. Check the Bugsink employed-api project for the event.')
"
```

### Frontend

Add `NEXT_PUBLIC_SENTRY_DSN` to `.env.local` and run `npm run dev`. A
`Sentry.captureMessage` call surfaces in the Bugsink `employed-web` project
within seconds.

## Source maps (optional)

`@sentry/nextjs` can upload source maps during `npm run build` when
`SENTRY_AUTH_TOKEN` is present. The Bugsink source-map flow is unproven, so
source-map upload stays **disabled** until it is validated as a separate pass —
keep `SENTRY_AUTH_TOKEN` unset for now.

## Legacy Sentry SaaS

The former Sentry SaaS org is retained **read-only** for historical events. Do
not create new Sentry SaaS projects for Employed — all new error tracking goes
to Bugsink.
