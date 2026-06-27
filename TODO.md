<!-- last_verified: 2026-06-27T00:00:00Z| git_ref: master

# Employed — TODO

Current open items only.

## Operator / production

- [ ] Wire Bugsink: create/confirm `employed-api` and `employed-web` projects, set production `SENTRY_DSN` values, and set `SENTRY_ENVIRONMENT=production`.
- [ ] Wire Gatus monitors for `https://joinemployed.com/` and `https://api.joinemployed.com/health`.
- [ ] Confirm Google OAuth and reCAPTCHA allowed origins include `mx.joinemployed.com` and `mz.joinemployed.com` if users authenticate directly on market hosts.
- [ ] Replace Stripe test keys with live keys and verify the live webhook when monetisation starts.
- [ ] Decide on persistent media storage for resume PDF artifacts; current artifacts are local/ephemeral on the EC2 host.
- [ ] Confirm M-Pesa/e-Mola sandbox or live credentials before claiming real mobile-money processing.

## Engineering

- [ ] Add frontend component tests for high-value tenant/application views.
- [ ] Pin or choose the HTML-to-PDF engine for enhanced resume rendering if local artifact generation becomes user-facing.
- [ ] Keep Alembic migrations append-only after `001`-`005`.

## Later

- [ ] Evaluate Cloudflare R2 for durable media storage.
- [ ] Add performance budgets and CDN/cache rules once traffic justifies them.
