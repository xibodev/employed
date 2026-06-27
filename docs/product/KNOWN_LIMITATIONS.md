# Employed — Known Limitations

```yaml
last_verified: 2026-06-27T00:00:00Z
git_ref: master
verified_by: prod documentation refresh
```

Current limitations in production.

## KL-01 — Resume artifacts are local and ephemeral

Resume PDF artifacts write to local `RESUME_ARTIFACT_DIR` on the EC2 host. They are not stored in durable object storage. Use Cloudflare R2 when persistent media is required.

## KL-02 — Bugsink is not wired

The backend and frontend SDKs are DSN-gated. `SENTRY_DSN` is empty in production, so error tracking no-ops until Bugsink DSNs are provisioned.

## KL-03 — Gatus monitors are not wired

Gatus is the uptime standard, but production checks for `joinemployed.com` and `api.joinemployed.com/health` are not configured yet.

## KL-04 — Market-host auth/bot origins need confirmation

Google OAuth and reCAPTCHA are configured for `joinemployed.com`. Confirm and add `mx.joinemployed.com` and `mz.joinemployed.com` origins if those hosts support direct auth or protected submissions.

## KL-05 — Stripe is test-mode only

Stripe is configured with test-mode keys. The production webhook endpoint exists, but live keys and live payment verification are deferred until monetisation starts.

## KL-06 — Mobile money is simulator-mode only

M-Pesa and e-Mola remain simulators. Real provider credentials, callback validation, and settlement flows are not active.

## KL-07 — Resume media persistence is not a solved product flow

The product can render resume artifacts, but the operator must choose retention, access, and cleanup policy before treating generated PDFs as durable user files.
