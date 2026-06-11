# ADR-005: Payment provider registry pattern

**Status:** Accepted — pattern survived the May 2026 rewrite; the registry now lives in `backend/app/payments/` (adapters `stripe_adapter.py`, `mpesa_adapter.py`, `emola_adapter.py`; market → provider mapping in `backend/app/services/market.py`). File paths below are the original Meteor implementation.  
**Date:** 2026 (A10.0)  
**Context:** The app started with Stripe-only payments. Mozambique's mobile-money ecosystem (M-Pesa via Vodacom, e-Mola via Movitel) requires additional providers. Each provider has different APIs, authentication, and settlement flows.  
**Decision:** Implement a registration-based provider registry (`server/lib/payments.js`) where each provider registers `{ key, name, markets, initiate(), status() }`. The checkout method (`featuredJob.initiate`) is provider-agnostic — it delegates to the registered provider.  
**Consequences:**
- Adding a new provider is a single file that calls `Payments.register()`
- Market → provider mapping is declarative in `both/lib/constants.js`
- Simulator mode is per-provider, so dev/test works without real API credentials
- The `PaymentIntents` collection tracks lifecycle uniformly across all providers
