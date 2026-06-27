<!-- last_verified: 2026-06-27T00:00:00Z| git_ref: master| verified_by: prod documentation refresh -->

# Uptime Monitoring — Employed

Gatus is the uptime monitoring standard for Employed.

## Production checks to wire

| Endpoint | Expected result |
|----------|-----------------|
| `https://joinemployed.com/` | 2xx HTML response |
| `https://www.joinemployed.com/` | 2xx/redirect to canonical frontend |
| `https://mz.joinemployed.com/` | 2xx MZ market frontend |
| `https://mx.joinemployed.com/` | 2xx MX market frontend |
| `https://api.joinemployed.com/health` | 200 JSON with `status: ok`, `db: ok`, `redis: ok` |

## Current state

The app exposes the health endpoints. Gatus checks for the production URLs are not yet configured.

## Alert expectations

- API health failure is P1 if it persists beyond one retry interval.
- Frontend host failure is P1 for apex and P2 for a single market alias.
- A degraded DB or Redis field in `/health` is P2 unless the API is fully down.

## See also

- `docs/operations-runbook.md`
- `backend/app/main.py` (`/health`)
- `frontend/src/app/api/health/route.ts`
