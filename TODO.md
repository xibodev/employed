<!-- last_verified: 2026-06-28T00:00:00Z| git_ref: master

# Employed — TODO

Current open items only.

## Operator / production

- [ ] Confirm Google OAuth and reCAPTCHA allowed origins include `mx.joinemployed.com` and `mz.joinemployed.com` if users authenticate directly on market hosts.
- [ ] Replace Stripe test keys with live keys and verify the live webhook when monetisation starts.
- [ ] Add a user-facing resume download endpoint; PDFs already persist to the R2 bucket `employed-prod-resumes` but no serve route exists.
- [ ] Confirm M-Pesa/e-Mola sandbox or live credentials before claiming real mobile-money processing.

## Engineering

- [ ] Add frontend component tests for high-value tenant/application views.
- [ ] Pin or choose the HTML-to-PDF engine for enhanced resume rendering if local artifact generation becomes user-facing.
- [ ] Keep Alembic migrations append-only after `001`-`005`.

## Later

- [ ] Add performance budgets and CDN/cache rules once traffic justifies them.
