---
last_verified: 2026-06-11T02:02:49Z
git_ref: fix/quality-run-2026-06-10 (uat baseline 00aa899)
verified_by: doc-drift audit, quality run 2026-06-10_120309
---

# Markets and Locales

> How subdomains, countries, languages, and pricing connect end-to-end.
> Hostnames below use the current UAT domain (`employed.xibodev.com`) as
> examples — the deployment domain itself is env-derived via
> `NEXT_PUBLIC_APP_URL` (Rule 2), never hardcoded.

## Market resolution

```
Hostname (first label)          Market key     Country    Default locale    Pricing
──────────────────────────────  ──────────     ───────    ──────────────    ────────────
mz.<app-domain>                 mz             MZ         pt                MZN 2,500
mx.<app-domain>                 mx             MX         es                MX$999
<app-domain> (apex)             mz (default)   MZ         pt                MZN 2,500
localhost / unknown             mz (default)   MZ         pt                MZN 2,500
```

### How it works (backend)

1. `MarketMiddleware` (`backend/app/middleware/market.py`) reads `X-Forwarded-Host` (preferred, EMP-001) then `Host` on every request — required because the frontend server proxies API calls, so the browser's host arrives via `X-Forwarded-Host`.
2. The first subdomain label (`mz`, `mx`) is looked up in `MARKETS` (`backend/app/services/market.py`).
3. If the subdomain doesn't match a known market, it falls back to `DEFAULT_MARKET_KEY = "mz"`.
4. The resolved market dict is stored in `request.state.market` and injected via `Depends(get_current_market)`.

> **Live-UAT note:** the deployed UAT build (`uat` @ `00aa899`) still ignores
> `X-Forwarded-Host`, so the MX host serves MZ data there until the fix
> branch deploys.

### Market definitions

```python
# backend/app/services/market.py
MARKETS = {
    "mz": {
        "country": "MZ",
        "locale": "pt",
        "featured_job": {"amount": 250000, "currency": "mzn", "label": "MZN 2,500"},
        "payment_providers": ["mpesa", "emola", "stripe"],
    },
    "mx": {
        "country": "MX",
        "locale": "es",
        "featured_job": {"amount": 99900, "currency": "mxn", "label": "MX$999"},
        "payment_providers": ["stripe"],
    },
}
```

### How it works (frontend)

`frontend/src/lib/market.ts` resolves the market from the hostname using the same subdomain logic, with all market hostnames derived from the single `NEXT_PUBLIC_APP_URL` env var (EMP-013 — no domain literals in `src/`). Components use it for market-aware pricing and locale defaults.

---

## Locale resolution

The UI supports three languages: **English (`en`)**, **Spanish (`es`)**, and **Portuguese (`pt`)**.

### How the locale is chosen

1. **Server-rendered copy** — `frontend/src/i18n/request.ts` (next-intl) resolves the locale from the request hostname: `mx.*` → `es`, everything else → `pt`.
2. **Header language selector** — persists the visitor's choice to `localStorage['employed_locale']` for client-side copy.

### Translation system

Translation catalogs live in `frontend/messages/` as JSON files keyed by locale (`en.json`, `es.json`, `pt.json`) — 263 keys per locale, kept in sync across all three (EMP-027).

Adding a translation is a three-file change — add the key to all three locale files.

Locale codes used throughout: `en`, `pt`, `es` (STANDARDS §4 — no extended tags like `pt-MZ`).

Known residuals (EMP-027): API-origin error strings remain English; job-type/currency/period option labels stay canonical API values; admin UI copy is English-only.

---

## Country assignment

When a job is created via `POST /jobs`:

1. Backend resolves the market from the request host via `get_current_market()`
2. `job.country` is **force-set** to `market["country"]` — any client-supplied value is ignored

This prevents cross-market pollution (e.g., posting an MX job from the MZ subdomain).

---

## SEO and locale

`frontend/src/lib/seo.ts` handles search-engine localization:

- Sets `<link rel="canonical">` and `<link rel="alternate" hreflang="...">` tags
- Uses `Intl.DateTimeFormat` with the current locale for date rendering

---

## Adding a new market

1. Add an entry to `MARKETS` in `backend/app/services/market.py` with `country`, `locale`, `featured_job` pricing, and `payment_providers`
2. Add the same entry to `frontend/src/lib/market.ts`
3. Add translations for any market-specific copy to all three locale files in `frontend/messages/`
4. Configure DNS — point `<key>.` + the deployment domain (current UAT: `<key>.employed.xibodev.com`) to the app
5. Add a Caddy reverse-proxy block for the new subdomain on Box 3
6. If the market uses a new locale, add a fourth translation file (and extend `frontend/src/i18n/request.ts`)
