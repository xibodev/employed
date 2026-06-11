# ADR-006: Subdomain-based market selection

**Status:** Accepted — still current after the May 2026 rewrite; implemented by `backend/app/middleware/market.py` (`X-Forwarded-Host`/`Host`) and `frontend/src/lib/market.ts` (hosts derived from `NEXT_PUBLIC_APP_URL`). The DDP reference below is Meteor-era.  
**Date:** Inherited from early development  
**Context:** Employed serves multiple countries (Mozambique, Mexico) with different languages, currencies, and payment providers. Options considered: path-based (`/mz/jobs`), query-param-based (`?market=mz`), or subdomain-based (`mz.employed.co.mz`).  
**Decision:** Use subdomain-based market selection. The first label of the hostname determines the active market. `lvh.me` is used for local development (resolves to 127.0.0.1).  
**Consequences:**
- Clean URLs — no market prefix cluttering paths
- SEO-friendly — each market gets its own crawlable subdomain
- Server-side market resolution works in both DDP (via connection headers) and HTTP (via `Host` header)
- Job creation is server-locked to the connection's market — prevents cross-market posting
- Adding a market requires a DNS entry + a `MARKETS` constant update
- Local dev requires `mz.lvh.me:3000` / `mx.lvh.me:3000` instead of plain `localhost`
