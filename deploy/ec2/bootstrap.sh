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
IMAGE_TAG="$(aws ssm get-parameter --name "$SSM_BASE/DEPLOY_IMAGE_TAG" --query 'Parameter.Value' --output text --region "$REGION")"
ASSETS_BUCKET="$(aws ssm get-parameter --name "$SSM_BASE/DEPLOY_ASSETS_BUCKET" --query 'Parameter.Value' --output text --region "$REGION")"
ECR="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"

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

# --- render .env from SSM, then pull + up ---
export EMPLOYED_API_IMAGE="${ECR}/employed-api:${IMAGE_TAG}"
"$APP_DIR/render-env.sh" "$APP_DIR/.env"

aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ECR"
cd "$APP_DIR"
docker compose pull
docker compose up -d

echo "bootstrap complete: ${EMPLOYED_API_IMAGE}"
