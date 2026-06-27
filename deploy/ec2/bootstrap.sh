#!/usr/bin/env bash
# =============================================================================
# bootstrap.sh — EC2 user-data for the Employed single-box API runtime.
# =============================================================================
# Self-contained, account-agnostic provisioner. Pass as the EC2 user-data on an
# Amazon Linux 2023 instance whose instance role can:
#   * ssm:GetParameter + kms:Decrypt on /employed/prod/*
#   * ecr:GetAuthorizationToken + pull from the employed-api repo
#   * s3:GetObject on the deploy-assets bucket
#   * AmazonSSMManagedInstanceCore (Session Manager)
#
# No account ID, secret, or token is baked in — the account is derived at boot
# and everything else is read from SSM. Idempotent enough to re-run.
set -euxo pipefail

REGION="us-east-1"
SSM_BASE="/employed/prod"
APP_DIR="/opt/employed"

ACCOUNT="$(aws sts get-caller-identity --query Account --output text --region "$REGION")"
ASSETS_BUCKET="$(aws ssm get-parameter --name "$SSM_BASE/DEPLOY_ASSETS_BUCKET" --query 'Parameter.Value' --output text --region "$REGION")"
ECR="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"

# DEPLOY_IMAGE_TAG is published by the deploy-prod pipeline's build-push job. On
# a first launch the box may boot BEFORE the first image is published, so wait
# for the parameter instead of hard-failing (handles the launch/build race).
IMAGE_TAG=""
for _ in $(seq 1 60); do
  IMAGE_TAG="$(aws ssm get-parameter --name "$SSM_BASE/DEPLOY_IMAGE_TAG" --query 'Parameter.Value' --output text --region "$REGION" 2>/dev/null || true)"
  [ -n "$IMAGE_TAG" ] && [ "$IMAGE_TAG" != "None" ] && break
  echo "waiting for ${SSM_BASE}/DEPLOY_IMAGE_TAG to be published..."
  sleep 20
done
if [ -z "$IMAGE_TAG" ] || [ "$IMAGE_TAG" = "None" ]; then
  echo "DEPLOY_IMAGE_TAG never appeared; aborting bootstrap." >&2
  exit 1
fi

# --- platform layer: docker + compose v2 plugin ---
dnf -y install docker
mkdir -p /usr/libexec/docker/cli-plugins
curl -fsSL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m)" \
  -o /usr/libexec/docker/cli-plugins/docker-compose
chmod +x /usr/libexec/docker/cli-plugins/docker-compose
systemctl enable --now docker

# --- app assets from S3 (single source of truth; uploaded from deploy/ec2/) ---
mkdir -p "$APP_DIR"
aws s3 cp "s3://${ASSETS_BUCKET}/ec2/docker-compose.ec2.yml" "$APP_DIR/docker-compose.yml" --region "$REGION"
aws s3 cp "s3://${ASSETS_BUCKET}/ec2/render-env.sh"          "$APP_DIR/render-env.sh"       --region "$REGION"
chmod +x "$APP_DIR/render-env.sh"

# --- render .env from SSM ---
export EMPLOYED_API_IMAGE="${ECR}/employed-api:${IMAGE_TAG}"
"$APP_DIR/render-env.sh" "$APP_DIR/.env"

aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ECR"
cd "$APP_DIR"
docker compose pull

# --- DB migrations BEFORE starting the app (idempotent; no-op when current).
# The compose stack has no migrate service, so run alembic via the api image.
# A failed migration must fail the deploy, not crash-loop a half-migrated app.
docker compose run --rm api alembic upgrade head

docker compose up -d --remove-orphans

# --- health gate: wait for the api container to report healthy ---
for i in $(seq 1 20); do
  status="$(docker inspect -f '{{.State.Health.Status}}' "$(docker compose ps -q api)" 2>/dev/null || echo starting)"
  [ "$status" = healthy ] && { echo "bootstrap complete: ${EMPLOYED_API_IMAGE}"; exit 0; }
  echo "waiting for api health ($i/20): ${status}"
  sleep 6
done
echo "api did not become healthy" >&2
docker compose ps
exit 1
