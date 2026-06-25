#!/usr/bin/env bash
#
# rollback-uat.sh — flip the UAT deployment on Box 3 back to a previous image.
#
# Every UAT deploy pushes an immutable `:uat-<sha>` image tag and records the
# active tag in /opt/employed/.env as IMAGE_TAG. This script repoints IMAGE_TAG
# at a prior SHA, pulls, and restarts — no rebuild required.
#
# Usage (run ON Box 3, from /opt/employed or anywhere):
#   scripts/rollback-uat.sh uat-<sha>
#   scripts/rollback-uat.sh <sha>          # bare SHA is accepted; uat- prefix added
#
# Find a previous SHA with: git log --oneline   (each UAT deploy == one uat commit)
# or list pushed tags:      docker images 'ghcr.io/mekjr1/employed-api'
#
# This is the rollback half of the SHA-pinning acceptance criterion: it flips
# Box 3 back to a known-good image in well under two minutes.

set -euo pipefail

DEPLOY_DIR="${EMPLOYED_DEPLOY_DIR:-/opt/employed}"
ENV_FILE="${DEPLOY_DIR}/.env"

if [ "$#" -ne 1 ] || [ -z "${1:-}" ]; then
  echo "Usage: $0 <image-tag-or-sha>" >&2
  echo "  e.g. $0 uat-1a2b3c4   or   $0 1a2b3c4" >&2
  exit 2
fi

TARGET="$1"
# Accept a bare commit SHA and normalise to the pushed tag form.
case "$TARGET" in
  uat-*) TAG="$TARGET" ;;
  *)     TAG="uat-${TARGET}" ;;
esac

if [ ! -f "$ENV_FILE" ]; then
  echo "Error: ${ENV_FILE} not found. Run this on Box 3 (or set EMPLOYED_DEPLOY_DIR)." >&2
  exit 1
fi

cd "$DEPLOY_DIR"

PREVIOUS="$(grep -E '^IMAGE_TAG=' "$ENV_FILE" | head -n1 | cut -d= -f2- || true)"
echo "Rolling back UAT: ${PREVIOUS:-<unset>} -> ${TAG}"

# Confirm the target image actually exists in the registry before we cut over.
if ! docker manifest inspect "ghcr.io/mekjr1/employed-api:${TAG}" >/dev/null 2>&1; then
  echo "Error: image ghcr.io/mekjr1/employed-api:${TAG} not found in registry." >&2
  echo "       Check the SHA, or that you are logged in to ghcr.io." >&2
  exit 1
fi

# Upsert IMAGE_TAG in .env (same helper shape as the deploy workflow).
if grep -q '^IMAGE_TAG=' "$ENV_FILE"; then
  sed -i "s#^IMAGE_TAG=.*#IMAGE_TAG=${TAG}#" "$ENV_FILE"
else
  printf 'IMAGE_TAG=%s\n' "$TAG" >> "$ENV_FILE"
fi

docker compose pull
docker compose run --rm migrate
docker compose up -d --remove-orphans

# Health gate so a bad rollback target is caught immediately.
for i in $(seq 1 10); do
  if curl -fsSo /dev/null http://localhost:3301/health; then
    echo "Rollback complete — backend healthy on ${TAG}."
    exit 0
  fi
  [ "$i" -eq 10 ] && { echo "Backend never became healthy after rollback to ${TAG}." >&2; exit 1; }
  echo "Waiting for backend ($i/10)..."
  sleep 6
done
