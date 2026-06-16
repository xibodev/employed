#!/usr/bin/env bash
# backend/scripts/create-uptimerobot-monitors.sh
#
# Idempotent helper that creates the *missing* UptimeRobot monitors for
# Employed using the v3 REST API. Already-existing monitors (matched by URL)
# are skipped.
#
# Required env (sourced from C:\Users\gafar\.xibodev\secrets\integrations\UPTIMEROBOT.env
# on the operator machine, or supplied directly):
#   UPTIMEROBOT_API_KEY  - the Main API Key from
#                          https://dashboard.uptimerobot.com/integrations
#                          (the "Main API key" row; format u<userId>-<hex>).
#                          Bearer auth, used by both v3 and (legacy) v2.
#
# Optional env:
#   API_HEALTH_URL       - default https://api.employed.xibodev.com/health
#   FRONTEND_URL         - default https://employed.xibodev.com/
#   INTERVAL_SECONDS     - default 300 (5 min, free-tier minimum)
#
# Exit codes:
#   0  - every intended monitor exists (created or already there)
#   1  - missing UPTIMEROBOT_API_KEY
#   2  - GET /v3/monitors call failed
#   3  - POST /v3/monitors call failed

set -euo pipefail

: "${UPTIMEROBOT_API_KEY:?UPTIMEROBOT_API_KEY must be set (Main API Key from dashboard.uptimerobot.com/integrations)}"

API_HEALTH_URL="${API_HEALTH_URL:-https://api.employed.xibodev.com/health}"
FRONTEND_URL="${FRONTEND_URL:-https://employed.xibodev.com/}"
INTERVAL_SECONDS="${INTERVAL_SECONDS:-300}"

API="https://api.uptimerobot.com/v3"
AUTH_HEADER="Authorization: Bearer ${UPTIMEROBOT_API_KEY}"

JQ="$(command -v jq || true)"
if [[ -z "${JQ}" ]]; then
  echo "[uptimerobot] ERROR: jq is required (apt-get install jq / brew install jq)" >&2
  exit 2
fi

echo "[uptimerobot] fetching existing monitors via v3..."
existing="$(curl -fsS -H "${AUTH_HEADER}" "${API}/monitors?limit=100" || true)"

if [[ -z "${existing}" ]] || [[ "$(echo "${existing}" | jq -r 'has("data")')" != "true" ]]; then
  echo "[uptimerobot] ERROR: GET /v3/monitors failed: ${existing}" >&2
  exit 2
fi

create_if_missing() {
  local friendly_name="$1"
  local url="$2"
  local norm_url="${url%/}"
  local existing_id
  existing_id="$(echo "${existing}" | jq -r --arg url "${norm_url}" \
    '.data[]? | select((.url | sub("/$"; "")) == $url) | .id' | head -n1)"
  if [[ -n "${existing_id}" ]]; then
    echo "[uptimerobot] EXISTS ${friendly_name} (id=${existing_id}, url=${url}) -- skipping"
    return 0
  fi

  echo "[uptimerobot] CREATING ${friendly_name} -> ${url}"
  local body
  body="$(jq -nc \
    --arg name "${friendly_name}" \
    --arg url "${url}" \
    --argjson interval "${INTERVAL_SECONDS}" \
    '{type:"HTTP", friendlyName:$name, url:$url, interval:$interval, timeout:30}')"

  local resp
  resp="$(curl -sS -X POST -H "${AUTH_HEADER}" -H "Content-Type: application/json" \
    --data-binary "${body}" "${API}/monitors")"

  local new_id
  new_id="$(echo "${resp}" | jq -r '.id // empty')"
  if [[ -z "${new_id}" ]]; then
    echo "[uptimerobot] ERROR: POST /v3/monitors failed: ${resp}" >&2
    return 1
  fi
  echo "[uptimerobot] CREATED ${friendly_name} -> id=${new_id} (record this in docs/operations/uptime-monitoring.md)"
}

failures=0
create_if_missing "employed-api-uat" "${API_HEALTH_URL}" || failures=$((failures+1))
create_if_missing "employed-frontend-uat" "${FRONTEND_URL}" || failures=$((failures+1))

if (( failures > 0 )); then
  echo "[uptimerobot] ${failures} monitor(s) failed; see errors above" >&2
  exit 3
fi

echo "[uptimerobot] done"