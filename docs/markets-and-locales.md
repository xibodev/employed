---
last_verified: 2026-06-28T00:00:00Z
git_ref: master
verified_by: prod documentation refresh
---

# Markets and Locales

Market and locale are derived from the request hostname. The deployment domain is config-driven by `NEXT_PUBLIC_APP_URL`.

## Production hosts

| Host | Market | Country | Default locale | Pricing |
|------|--------|---------|----------------|---------|
| `joinemployed.com` | `mz` | MZ | `pt` | MZN 2,500 |
| `www.joinemployed.com` | `mz` | MZ | `pt` | MZN 2,500 |
| `mz.joinemployed.com` | `mz` | MZ | `pt` | MZN 2,500 |
| `mx.joinemployed.com` | `mx` | MX | `es` | MX$999 |
| localhost/unknown | `mz` | MZ | `pt` | MZN 2,500 |

## Backend resolution

`MarketMiddleware` reads `X-Forwarded-Host` first, then `Host`. The first hostname label is matched against `MARKETS`; unknown labels fall back to `mz`. The resolved market lands on `request.state.market` and is echoed through `X-Market`.

## Frontend resolution

`frontend/src/lib/market.ts` mirrors backend resolution and derives market hosts from `NEXT_PUBLIC_APP_URL`. The API client forwards the browser/server host as `X-Forwarded-Host`.

## Locales

The UI supports `en`, `pt`, and `es`. `mx.*` defaults to `es`; all other production hosts default to `pt`. Locale catalogs live in `frontend/messages/`.

## Job country assignment

When a job is created, the backend sets `job.country` from the active market. Client-supplied country values do not override the resolved market.

## Adding a market

Add the market to backend and frontend market registries, add locale coverage if needed, configure DNS/Tunnel/Vercel routing, and add test coverage for hostname resolution.
