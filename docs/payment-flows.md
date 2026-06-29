---
last_verified: 2026-06-28T00:00:00Z
git_ref: master
verified_by: prod documentation refresh
---

# Payment Flows

Employers can promote a job listing to featured status by paying a market-specific fee.

## Providers

| Market | Providers | Currency | Amount | Current state |
|--------|-----------|----------|--------|---------------|
| MZ | Stripe, M-Pesa, e-Mola | MZN | 2,500.00 | Stripe test mode; mobile money simulator mode |
| MX | Stripe | MXN | 999.00 | Stripe test mode |

Featured status lasts 30 days from settlement. If a job is already featured, the new period extends from the existing expiry date.

## Stripe

Stripe uses test-mode keys in production while Employed is pre-revenue. The production webhook endpoint is registered at `https://api.joinemployed.com/_stripe/webhook`. Live keys and live webhook verification are required before real charges.

## M-Pesa and e-Mola

M-Pesa and e-Mola run in simulator mode. Real provider credentials, callback signing, and settlement verification are not active.

## Data model

`PaymentIntent` tracks provider, amount, currency, status, external references, and settlement state. Settlement extends `job.featured_through` and records the payment result.

## Security

Webhook handlers verify provider signatures where configured and use Redis-backed replay protection. Secret values live in SSM SecureStrings.
