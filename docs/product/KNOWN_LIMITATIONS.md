# Employed — Known Limitations

```yaml
last_verified: 2026-06-28T00:00:00Z
git_ref: master
verified_by: prod documentation refresh
```

Current limitations in production.

## KL-01 — Resume download is not yet user-facing

Resume PDFs are generated and persisted durably to the Cloudflare R2 bucket `employed-prod-resumes`. There is no user-facing serve/download endpoint yet; the storage layer exists but no route exposes the artifacts.

## KL-02 — Market-host auth/bot origins need confirmation

Google OAuth and reCAPTCHA are configured for `joinemployed.com`. Confirm and add `mx.joinemployed.com` and `mz.joinemployed.com` origins if those hosts support direct auth or protected submissions.

## KL-03 — Stripe is test-mode only

Stripe is configured with test-mode keys. The production webhook endpoint exists, but live keys and live payment verification are deferred until monetisation starts.

## KL-04 — Mobile money is simulator-mode only

M-Pesa and e-Mola remain simulators. Real provider credentials, callback validation, and settlement flows are not active.
