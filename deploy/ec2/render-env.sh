#!/usr/bin/env bash
# =============================================================================
# render-env.sh — assemble /opt/employed/.env for the EC2 compose runtime.
# =============================================================================
# Runs ON the EC2 host using the instance role (ssm:GetParameter + kms:Decrypt
# on /employed/prod/*). Pulls SecureString secrets from SSM and appends static,
# non-secret runtime config for the production API. Static values can be
# overridden by creating same-named SSM parameters under /employed/prod/.
#
# Usage:  EMPLOYED_API_IMAGE=<ecr-image> ./render-env.sh [/opt/employed/.env]
#
# The output file holds live secrets — it is chmod 600 and MUST NOT be committed.
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
SSM_BASE="/employed/prod"
OUT="${1:-/opt/employed/.env}"
IMAGE="${EMPLOYED_API_IMAGE:?set EMPLOYED_API_IMAGE to the immutable ECR image (e.g. <acct>.dkr.ecr.us-east-1.amazonaws.com/employed-api:prod-<sha>)}"

ssm() {
  aws ssm get-parameter --name "$SSM_BASE/$1" --with-decryption \
    --query 'Parameter.Value' --output text --region "$REGION"
}

ssm_or_default() {
  local name="$1"
  local default="$2"
  aws ssm get-parameter --name "$SSM_BASE/$name" --with-decryption \
    --query 'Parameter.Value' --output text --region "$REGION" 2>/dev/null || printf '%s\n' "$default"
}

umask 077
tmp="${OUT}.tmp.$$"
{
  echo "# rendered by render-env.sh at $(date -u +%FT%TZ) — DO NOT COMMIT (live secrets)"
  echo "EMPLOYED_API_IMAGE=${IMAGE}"

  # --- secrets from SSM SecureString (/employed/prod/*) ---
  echo "DATABASE_URL=$(ssm DATABASE_URL)"
  echo "SECRET_KEY=$(ssm SECRET_KEY)"
  echo "STRIPE_SECRET_KEY=$(ssm STRIPE_SECRET_KEY)"
  echo "STRIPE_WEBHOOK_SECRET=$(ssm STRIPE_WEBHOOK_SECRET)"
  echo "STRIPE_PUBLISHABLE_KEY=$(ssm STRIPE_PUBLISHABLE_KEY)"
  echo "IP_SALT=$(ssm IP_SALT)"
  echo "RECAPTCHA_SECRET_KEY=$(ssm RECAPTCHA_SECRET_KEY)"
  echo "NEXT_PUBLIC_RECAPTCHA_SITE_KEY=$(ssm NEXT_PUBLIC_RECAPTCHA_SITE_KEY)"
  echo "GOOGLE_CLIENT_ID=$(ssm GOOGLE_CLIENT_ID)"
  echo "GOOGLE_CLIENT_SECRET=$(ssm GOOGLE_CLIENT_SECRET)"
  echo "SMTP_USERNAME=$(ssm SMTP_USERNAME)"
  echo "SMTP_PASSWORD=$(ssm SMTP_PASSWORD)"
  echo "CLOUDFLARED_TOKEN=$(ssm CLOUDFLARED_TOKEN)"
  echo "SENTRY_DSN=$(ssm_or_default SENTRY_DSN '')"

  # --- static runtime config (overridable by optional SSM params) ---
  echo "REDIS_URL=$(ssm_or_default REDIS_URL 'redis://redis:6379/0')"
  echo "JWT_ALGORITHM=$(ssm_or_default JWT_ALGORITHM 'HS256')"
  echo "ACCESS_TOKEN_EXPIRE_MINUTES=$(ssm_or_default ACCESS_TOKEN_EXPIRE_MINUTES '30')"
  echo "REFRESH_TOKEN_EXPIRE_DAYS=$(ssm_or_default REFRESH_TOKEN_EXPIRE_DAYS '7')"
  echo "SMTP_HOST=$(ssm_or_default SMTP_HOST 'email-smtp.us-east-1.amazonaws.com')"
  echo "SMTP_PORT=$(ssm_or_default SMTP_PORT '587')"
  echo "SMTP_USE_TLS=$(ssm_or_default SMTP_USE_TLS 'true')"
  echo "SMTP_USE_SSL=$(ssm_or_default SMTP_USE_SSL 'false')"
  echo "FROM_EMAIL=$(ssm_or_default FROM_EMAIL 'Employed <noreply@joinemployed.com>')"
  echo "ADMIN_EMAIL=$(ssm_or_default ADMIN_EMAIL 'admin@joinemployed.com')"
  echo "ENVIRONMENT=$(ssm_or_default ENVIRONMENT 'production')"
  echo "FRONTEND_BASE_URL=$(ssm_or_default FRONTEND_BASE_URL 'https://joinemployed.com')"
  echo "NEXT_PUBLIC_APP_URL=$(ssm_or_default NEXT_PUBLIC_APP_URL 'https://joinemployed.com')"
  echo "NEXT_PUBLIC_API_URL=$(ssm_or_default NEXT_PUBLIC_API_URL 'https://api.joinemployed.com')"
  echo "CORS_ORIGINS=$(ssm_or_default CORS_ORIGINS 'https://joinemployed.com,https://www.joinemployed.com,https://mx.joinemployed.com,https://mz.joinemployed.com')"
  echo "SENTRY_ENVIRONMENT=$(ssm_or_default SENTRY_ENVIRONMENT 'production')"
} > "$tmp"
mv "$tmp" "$OUT"
chmod 600 "$OUT"
echo "wrote $OUT ($(wc -l < "$OUT") lines)"
