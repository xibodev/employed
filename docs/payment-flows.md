---
last_verified: 2026-06-11T02:02:49Z
git_ref: fix/quality-run-2026-06-10 (uat baseline 00aa899)
verified_by: doc-drift audit, quality run 2026-06-10_120309
---

# Payment Flows

> How featured-job payments work across all three providers.
>
> **Live-UAT note:** the mandatory callback timestamp + Redis replay dedupe
> on mobile-money webhooks (EMP-019) exists only on the unmerged branch
> `fix/quality-run-2026-06-10`; the deployed UAT build does not enforce it yet.

## Overview

Employers can promote a job listing to "featured" status by paying a
market-specific fee. The payment system supports three providers, selected
per market:

| Market | Providers | Currency | Amount | Label |
|--------|-----------|----------|--------|-------|
| MZ (Mozambique) | M-Pesa, e-Mola, Stripe | MZN | 2,500.00 | MZN 2,500 |
| MX (Mexico) | Stripe | MXN | 999.00 | MX$999 |

Featured status lasts **30 days** from payment settlement. If a job is
already featured, the new period extends from the existing expiry date.

---

## Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌───────────────────────────┐
│   Browser    │────▶│  POST            │────▶│  payments.py router       │
│  (checkout)  │     │  /payments/      │     │  (FastAPI)                │
└─────────────┘     │  initiate        │     └───────────┬───────────────┘
                    └──────────────────┘                 │
                                          ┌──────────────┼──────────────┐
                                          ▼              ▼              ▼
                                    ┌──────────┐  ┌──────────┐  ┌──────────┐
                                    │  Stripe  │  │  M-Pesa  │  │  e-Mola  │
                                    │ adapter  │  │ adapter  │  │ adapter  │
                                    └────┬─────┘  └────┬─────┘  └────┬─────┘
                                         │              │              │
                                         ▼              ▼              ▼
                                    ┌──────────┐  ┌──────────────────────────────┐
                                    │  Stripe  │  │  Webhook callback            │
                                    │  API     │  │  /webhooks/_mpesa/callback   │
                                    └────┬─────┘  │  /webhooks/_emola/callback   │
                                         │        └──────────────┬───────────────┘
                                         ▼                   ▼
                                    ┌────────────────────────────────────┐
                                    │  payments/settlement.py            │
                                    │  Extends job.featured_through      │
                                    │  Updates PaymentIntent.status      │
                                    └────────────────────────────────────┘
```

---

## Payment lifecycle

### States

The `PaymentIntent` model tracks every payment attempt:

| Status | Meaning |
|--------|---------|
| `pending` | Intent created, provider not yet contacted |
| `awaiting_user` | Mobile-money: waiting for user to confirm on phone |
| `completed` | Payment settled, featured extension applied |
| `failed` | Payment rejected or timed out |
| `cancelled` | User cancelled before completion |
| `expired` | TTL expired without settlement |

### Key fields

| Field | Description |
|-------|-------------|
| `job_id` | The job being featured |
| `provider_key` | `"stripe"`, `"mpesa"`, or `"emola"` |
| `provider_ref` | Provider-specific reference (Stripe session ID, transaction ref) |
| `amount` / `currency` | Charged amount |
| `payer_msisdn` / `payer_msisdn_hash` | Last 4 digits stored verbatim; full MSISDN only as a salted hash (mobile money) |
| `extended_through` | Resulting `featured_through` date |
| `simulator` | `true` if settled via simulator |

---

## Provider: Stripe

**Markets:** MX, MZ

**Flow:**
1. Client calls `POST /payments/initiate` with `provider_key: "stripe"` (returns `201`)
2. Backend creates a Stripe Checkout Session via `stripe.checkout.sessions.create()`
3. `PaymentIntent` inserted with `status: "pending"`, `provider_ref: session.id`
4. Client receives `{ kind: "redirect", redirect_url: session.url }` and redirects
5. After payment, Stripe sends webhook to `POST /webhooks/_stripe/webhook`
   (the router is mounted under `/webhooks` — the bare `/_stripe/webhook` path
   404s; the Stripe dashboard endpoint URL must include the prefix)
6. Handler verifies `Stripe-Signature` header, processes event, calls settlement

**Webhook events handled:**

| Event | Action |
|-------|--------|
| `checkout.session.completed` | Settle → extend featured |
| `checkout.session.async_payment_succeeded` | Same |
| `checkout.session.async_payment_failed` | Mark intent `failed` |
| `charge.refunded` | Remove featured status |
| `charge.dispute.created` | Remove featured status |

**Idempotency:** Webhook replay cache (`webhooks/replay_cache.py`) deduplicates events by `event_id` — duplicate deliveries are safe.

**Configuration:**
- `STRIPE_SECRET_KEY` — required in production
- `STRIPE_WEBHOOK_SECRET` — required; rotate per endpoint in Stripe dashboard
- `STRIPE_PUBLISHABLE_KEY` — publishable key, read by the backend as runtime config (passthrough to the client)

---

## Provider: M-Pesa (Vodacom Mozambique)

**Markets:** MZ only

**MSISDN validation:** Must start with `84` or `85` (Vodacom MZ prefixes).

**Simulator mode:** Controlled by `MPESA_SIMULATOR` (default `true`). While
the simulator is on, no real API calls are made — settlement fires after a
short delay. The live (non-simulator) adapter path is deliberately not
implemented yet.

**Flow:**
1. Client calls `POST /payments/initiate` with `provider_key: "mpesa"`, `payer_msisdn: "84..."` (returns `201`)
2. Server validates MSISDN, creates `PaymentIntent` with `status: "awaiting_user"` (only the last 4 MSISDN digits are stored)
3. In simulator mode: settlement fires after the configured delay
4. In live mode: callback received at `POST /webhooks/_mpesa/callback`
5. Settlement extends `featured_through` by 30 days

**Webhook verification:** HMAC-SHA256 (constant-time compare).
Expected header: `x-mpesa-signature` or `x-callback-signature`.
The callback payload **must** carry a timestamp within 5 minutes —
callbacks without one are rejected with `400` — and deliveries are
replay-deduped via Redis.

**Configuration:**
- `MPESA_SIMULATOR` — adapter mode (default `true`)
- `MPESA_WEBHOOK_SECRET` — required for live webhook verification

---

## Provider: e-Mola (Movitel Mozambique)

**Markets:** MZ only

**MSISDN validation:** Must start with `86` or `87` (Movitel MZ prefixes).

**Simulator mode:** Controlled by `EMOLA_SIMULATOR` (default `true`).

**Flow:** Same as M-Pesa — MSISDN validation, `awaiting_user`, simulator
settlement or live webhook at `POST /webhooks/_emola/callback` (header
`x-emola-signature`/`x-callback-signature`; same mandatory-timestamp and
replay-dedupe rules).

**Configuration:**
- `EMOLA_SIMULATOR` — adapter mode (default `true`)
- `EMOLA_WEBHOOK_SECRET` — required for live webhook verification

---

## Error handling

### Initiation errors

`POST /payments/initiate` validates before calling the provider:
- User must be authenticated and email-verified
- User must own the job
- Job must be in `pending` or `active` status
- Provider must be available for the **current market** (resolved from the request host)
- An existing open intent for the same job is returned as-is instead of creating a duplicate

If the provider's adapter throws, the intent is marked `failed` and `400` is returned.

### Cancellation

`POST /payments/{intent_id}/cancel` applies to non-terminal intents only.

### Webhook resilience

- **Stripe:** Internal errors return `200` to prevent Stripe retry storms; the error is logged.
- **Mobile money:** Settlement is idempotent — terminal intents are skipped on repeated callbacks.
