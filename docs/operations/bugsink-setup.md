<!-- last_verified: 2026-06-27T00:00:00Z| git_ref: master| verified_by: prod documentation refresh -->

# Error Tracking Setup — Bugsink

Bugsink is the error-tracking standard. Employed uses Sentry-SDK-compatible clients and sends events only when `SENTRY_DSN` is set.

## Current state

- Backend `sentry-sdk[fastapi]` wiring exists.
- Frontend `@sentry/nextjs` wiring exists.
- Production `SENTRY_DSN` is empty, so both SDKs no-op.

## Required env

| Variable | Consumer | Notes |
|----------|----------|-------|
| `SENTRY_DSN` | backend, frontend server/edge | Bugsink DSN when provisioned |
| `NEXT_PUBLIC_SENTRY_DSN` | browser frontend | public Bugsink DSN when browser reporting is enabled |
| `SENTRY_ENVIRONMENT` | backend/frontend | `production` in prod |
| `SENTRY_TRACES_SAMPLE_RATE` | backend/frontend | optional sampling |

Values live in SSM SecureStrings or Vercel environment settings as appropriate. Do not commit DSN values.

## Provisioning checklist

1. Create/confirm Bugsink projects `employed-api` and `employed-web`.
2. Store backend DSN in `/employed/prod/SENTRY_DSN` if backend reporting is enabled.
3. Configure Vercel frontend DSN env if browser/server reporting is enabled.
4. Set `SENTRY_ENVIRONMENT=production`.
5. Deploy and send a test event from backend and frontend.
6. Add the event links to the operational handoff, not to fixed architecture docs.

## Local development

Leave DSNs unset locally unless intentionally testing Bugsink.
