# ADR-006: Subdomain-based market selection

**Status:** Accepted. Current production hosts are `joinemployed.com`, `mz.joinemployed.com`, and `mx.joinemployed.com`; the old `.mz` examples in this ADR are historical examples only.
**Date:** Inherited from early development
**Context:** Employed serves multiple countries with different languages, currencies, and payment providers. Options considered: path-based (`/mz/jobs`), query-param-based (`?market=mz`), or subdomain-based market hosts.
**Decision:** Use subdomain-based market selection. The first label of the hostname determines the active market. `lvh.me` is used for local development.
**Consequences:**
- Clean URLs use market-specific hosts.
- Each market can have crawlable hostnames.
- Server-side market resolution uses `X-Forwarded-Host` or `Host`.
- Job creation is server-locked to the resolved market.
- Adding a market requires DNS/routing plus backend and frontend market registry updates.
- Local dev uses `mz.lvh.me:3000` and `mx.lvh.me:3000` when hostname-specific behavior is under test.
