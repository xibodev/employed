---
last_verified: 2026-06-11T02:02:49Z
git_ref: fix/quality-run-2026-06-10 (uat baseline 00aa899)
verified_by: doc-drift audit, quality run 2026-06-10_120309 (repo claims re-checked; monitor IDs/status from the 2026-05-29 live API probe)
---

# UptimeRobot Monitors -- employed.xibodev.com

> Status: **LIVE.** Both intended monitors exist and are reporting UP
> (last live-probed 2026-05-29).

## Active monitors

| Monitor name | Monitor ID | URL | Status | Created |
|---|---|---|---|---|
| `employed.xibodev.com` (frontend) | `803170467` | `https://employed.xibodev.com` | UP | 2026-05-27 |
| `employed-api-uat` (api) | `803177488` | `https://api.employed.xibodev.com/health` | UP | 2026-05-29 |

Confirmed via `GET https://api.uptimerobot.com/v3/monitors` (Bearer auth).
Account `mekjr1@gmail.com`, free tier (50-monitor limit, 21 used).

## How API auth actually works (corrected 2026-05-29)

The earlier doc claimed the stored key was "read-only" and that a separate
`ur`-prefixed Main API Key was needed. That was wrong. The correct facts:

- The key in `C:\Users\gafar\.xibodev\secrets\integrations\UPTIMEROBOT.env`
  (format `u<userId>-<hex>`) **IS the Main API Key**. UR displays the same
  value on `https://dashboard.uptimerobot.com/integrations` under the "Main
  API key" row. The "Read-only API key" row in that UI is a separate,
  optional key that has not been created.
- UR moved its write methods to **v3** (Bearer auth, JSON bodies, camelCase
  field names). The v2 `newMonitor` endpoint returns the misleading
  `access_denied: "You are not allowed to use some settings with your
  current plan"` for ANY parameter combination on free-tier accounts; this
  is not a paywall, it is v2 being deprecated.
- v2 `getMonitors`, `getAccountDetails`, and `editMonitor` still work.

## Recreating the monitors from scratch

```bash
export UPTIMEROBOT_API_KEY="$(grep ^UPTIMEROBOT_API_KEY= ~/.xibodev/secrets/integrations/UPTIMEROBOT.env | cut -d= -f2)"
bash backend/scripts/create-uptimerobot-monitors.sh
```

The script is idempotent -- it lists monitors via `GET /v3/monitors`, skips
any whose URL already exists, and creates only the missing ones.

## Manual v3 API examples

List Employed monitors:

```bash
curl -sS -H "Authorization: Bearer $UPTIMEROBOT_API_KEY" \
  "https://api.uptimerobot.com/v3/monitors?search=employed" | jq '.data[] | {id, friendlyName, url, status}'
```

Create a new monitor (request body is JSON, fields are camelCase):

```bash
curl -sS -X POST -H "Authorization: Bearer $UPTIMEROBOT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"type":"HTTP","friendlyName":"some-name","url":"https://example.com/health","interval":300,"timeout":30}' \
  "https://api.uptimerobot.com/v3/monitors"
```

## See also

- `_integrations/BOXES.md` -- `UPTIMEROBOT_API_KEY` is a shared GH secret in `mekjr1/.github`
- `_integrations/_brain_data/decisions/DEC-0002.md` -- the HEAD/405 bug that motivated the regression test
- `backend/app/main.py` -- `/health` accepts `GET` and `HEAD`
- `backend/tests/test_observability.py::test_health_accepts_head_for_uptimerobot` -- regression
- `docs/operations/oncall.md` -- alert routing