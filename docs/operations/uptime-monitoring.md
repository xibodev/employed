<!-- last_verified: 2026-06-15T00:00:00Z | git_ref: fix/quality-run-2026-06-10 | verified_by: self-contained cleanse 2026-06-15 (monitor IDs/status from the 2026-05-29 live UptimeRobot probe) -->

# Uptime Monitoring — employed.xibodev.com

> **Standard going forward:** **Gatus** on Box 0 (replaced UptimeRobot as the
> portfolio uptime standard, 2026-06-10).
>
> **Current live state:** Employed's monitors still run on **UptimeRobot** and
> are reporting UP. Migration to Gatus is pending — until then, the UptimeRobot
> monitors below remain the live source of truth.

## Target — Gatus (Box 0)

Gatus runs on Box 0 and probes each product's health endpoint on an interval.
Onboarding Employed means adding endpoint entries for:

- `https://employed.xibodev.com/` (frontend)
- `https://api.employed.xibodev.com/health` (API — expects `{"status":"ok"}`)

Gatus config is maintained on Box 0, outside this repo. Once Employed's
endpoints are added there and confirmed green, retire the UptimeRobot monitors
below.

## Current — UptimeRobot monitors (legacy, live)

| Monitor name | Monitor ID | URL | Status | Created |
|---|---|---|---|---|
| `employed.xibodev.com` (frontend) | `803170467` | `https://employed.xibodev.com` | UP | 2026-05-27 |
| `employed-api-uat` (api) | `803177488` | `https://api.employed.xibodev.com/health` | UP | 2026-05-29 |

Confirmed via `GET https://api.uptimerobot.com/v3/monitors` (Bearer auth).

### UptimeRobot API notes

- The UptimeRobot API key is referenced by name only (a GitHub secret /
  operator-local env file) — never committed here.
- UptimeRobot write methods live on **v3** (Bearer auth, JSON bodies, camelCase
  fields). The deprecated v2 `newMonitor` returns a misleading
  `access_denied: "...current plan"` for any parameters on free-tier accounts —
  this is v2 deprecation, not a paywall. v2 `getMonitors` / `getAccountDetails`
  / `editMonitor` still work.

### Recreating the UptimeRobot monitors

```bash
export UPTIMEROBOT_API_KEY="<from your local UptimeRobot env file>"
bash backend/scripts/create-uptimerobot-monitors.sh
```

The script is idempotent — it lists monitors via `GET /v3/monitors`, skips any
whose URL already exists, and creates only the missing ones.

List Employed monitors manually:

```bash
curl -sS -H "Authorization: Bearer $UPTIMEROBOT_API_KEY" \
  "https://api.uptimerobot.com/v3/monitors?search=employed" \
  | jq '.data[] | {id, friendlyName, url, status}'
```

## See also

- `backend/app/main.py` — `/health` accepts `GET` and `HEAD`
- `backend/tests/test_observability.py::test_health_accepts_head_for_uptimerobot`
  — regression for the HEAD/405 bug that motivated the monitor
- `docs/operations/oncall.md` — alert routing
