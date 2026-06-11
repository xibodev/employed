# Employed · Ads strategy

Status: **draft · v1** · 2026-05-22

> **Implementation note (2026-06-10):** this strategy was written against the
> retired Meteor app — the code links below (`server/*.js`,
> `client/views/*`) no longer exist, and the Phase-0 mock `adSlot` component
> was **not** carried into the current Next.js frontend (no ad surfaces are
> implemented today). The market/economics analysis still stands as product
> strategy; the implementation plan needs re-scoping against
> `frontend/src/components/` before any phase ships.

> Goal: **cover ~$20/mo server cost within 60 days**, without breaking the
> trust the employer side (the actual revenue) is built on. AdSense is a
> *fallback*, not the primary tool.

## Why we are not copying SeloPro's strategy

SeloPro is a free directory with no native B2B monetization rail — they
need AdSense because there is no other revenue surface. Employed already
ships a Stripe-backed **featured-job** flow ([`server/stripe.js`](../server/stripe.js),
[`client/views/jobs/jobForms.js`](../client/views/jobs/jobForms.js)). Direct
advertiser-side revenue out of that flow runs at **5–10× the RPM** an ad
network would pay for the same impressions, with zero third-party JS, no
consent banner, and no risk to job-seeker conversion.

So: use what we have first; only fall back to ad networks if Tiers 1 + 2
do not clear the server bill on their own.

## Reality check on AdSense in MZ

- AdSense MZ effective RPM is roughly **$0.20–$1.50** (low-end emerging
  market). At $0.50, $20/mo = **~40k ad impressions/month** = several
  hundred daily visitors hitting ~2 ad pages each.
- AdSense MZ approval typically takes weeks. Payout threshold is **$100**
  via international wire (no M-Pesa). At $20/mo, **first payout sits ~5
  months away**.
- Personalized ads (the high-RPM kind) require an LPDP/GDPR-style consent
  banner → friction → fewer job applications → kills *employer-side*
  revenue.

The honest conclusion: do not lead with AdSense.

## Three-tier revenue stack

Stacked in order of RPM and UX cost. Always fill the highest-RPM tier
first; only fall back when it is empty.

### Tier 1 — Featured / boosted listings *(advertiser-side, already built)*

The Stripe rail for featured jobs is already the highest-RPM "ad" the
site serves. Expand it:

| Product | Price (MZN) | Duration | Surface |
|---|---|---|---|
| Featured job *(exists)* | per [`MARKETS[*].featuredJob`](../both/lib/constants.js) | 30 days | top of `/jobs` |
| **Urgent hiring badge** *(new)* | ~250 MZN ($4) | 7 days | red badge on card |
| **Homepage spotlight** *(new)* | ~1 500 MZN ($25) | 7 days | single card above `/` hero |

Three urgent badges + one homepage spotlight per month = **$37/mo from one
employer pipeline**. Already covers servers. No third-party JS, no
privacy banner, no AdSense.

### Tier 2 — Direct sponsor slots *(local advertisers, cash)*

Sell one fixed slot at a time to local advertisers — no ad network in the
loop:

- **Target buyers (Maputo):** recruitment agencies, CV-writing services,
  vocational schools, training institutes, language coaches, co-working
  spaces.
- **Format:** branded card matching `jobSmall` styling, "Patrocinado por"
  label, fixed monthly price.
- **Price floor:** 1 500–2 000 MZN/month ($25–32). **One sale covers the
  entire infrastructure cost.**
- **Tech:** zero — JSON entry in [`both/lib/constants.js`](../both/lib/constants.js)
  plus a Blaze partial. No ad network, no consent, no compliance.

**This is the recommended Phase 1.** Get one sponsor signed *before* any
AdSense integration is written.

### Tier 3 — AdSense fallback *(only if Tiers 1+2 underperform)*

Conservative setup:

- **Non-personalized ads only** (`data-npa="1"`). ~30 % lower RPM, but
  **no consent banner needed** under LPDP — ships faster, does not kill
  apply-flow conversion.
- **One unit, one surface:** `in-feed` between the 8th and 9th card on
  `/jobs`, nowhere else, on first launch.
- **Lazy mount via `IntersectionObserver`** so it does not block LCP.
- **Geographic arbitrage:** MX market RPM is ~5–10× MZ. Tag ad calls with
  `market` so per-market RPM is visible.

## Surface map

### Allowed

| Slot id | Page | Position | Tier order | Notes |
|---|---|---|---|---|
| `home-spotlight` | `/` (`home` route) | Below the recent-jobs section, above the footer | T1 → T2 | One slot, never AdSense |
| `feed-sponsor` | `/jobs` (`jobs` route) | After the 8th result card (when available), and at the foot of the result list | T1 → T2 → T3 | Max 1 in-feed + 1 footer per page |
| `empty-state` | 404, "no jobs found" empty states | Inside the empty-state container | T2 → T3 | Optional |

### Forbidden — never

- `/jobs/:_id/:slug` (`job` route) — **apply-intent moment**, the page
  that drives conversions. Touch this and you lose employer trust.
- `/post-a-job` (`jobNew` / `jobNewAlias`), `/jobs/:_id/edit` (`jobEdit`),
  `/myjobs` (`myJobs`), `/account` (`userAccount`) — employer / user
  surfaces; they are *buying* not viewing.
- `/admin/*` (`adminJobs`) — internal.
- `/sign-in`, `/sign-up`, `/forgot-password`, `/reset-password/:token`,
  `/verify-email/:token` — auth flows; A9.32 just landed and is not
  worth risking.
- Modals, toasts, sticky / anchor / vignette / interstitial formats.

## Engineering rules

- **Component of record:** [`client/views/includes/adSlot.html`](../client/views/includes/adSlot.html) +
  [`adSlot.js`](../client/views/includes/adSlot.js). Single chokepoint.
- **Allowlist enforced in the component, not the call site.** `AdSlot`
  checks `Router.current().route.getName()` against `AD_ALLOWED_ROUTES`
  in [`both/lib/constants.js`](../both/lib/constants.js) and renders
  `null` on anything else. Do not trust call sites — a future operator
  will forget the `suppress` prop.
- **Auto-suppress for paying users:** any user with an active featured
  job (`featuredThrough > now`) sees no ads. Cheap quality signal.
- **Auto-suppress for admins:** `Roles.userIsInRole(uid, ['admin'])`.
- **Mock mode first:** `settings.public.ads.mock = true` renders a
  styled placeholder; **no AdSense JS loads in Phase 0 / 1 / 2**.
- **CSP additions** (gated on `settings.public.ads.enabled` once
  AdSense ships in Phase 3), to be added in
  [`server/security-headers.js`](../server/security-headers.js):
  - `script-src`: `https://pagead2.googlesyndication.com`
  - `frame-src`: `https://googleads.g.doubleclick.net https://tpc.googlesyndication.com`
  - `img-src`: add `https://*.g.doubleclick.net data:`
- **CLS budget:** reserve `min-height: 200px` per slot. Native ad units
  are the worst layout-shift offenders.
- **Frequency cap (Phase 3+):** if the user reloads `/jobs` more than 3
  times in one session, the in-feed slot stops rendering. Same eyeballs,
  no new value.

## House-ad fallback *(the secret weapon)*

When AdSense returns no fill OR an ad-blocker is detected, render an
**upsell card for the featured-job product** instead:

> *"Get your job to the top of this page. From 250 MZN. [Boost your
> listing →]"*

Converts the two groups that hurt the most (ad-blocker users +
no-fill impressions) into the group that pays (featured-job buyers).

## Kill rules

Hard floors. Walk away if hit:

- **Apply-flow conversion** (job view → external apply click) drops
  > 3 % week-over-week → roll back ads on that surface.
- **AdSense 14-day RPM < $0.30** → drop AdSense entirely; refocus on
  Tiers 1 + 2.
- **Single complaint from a paying employer about ads on their job's
  detail page** → emergency audit of the suppress logic.

## Phasing

| Phase | Scope | Done when |
|---|---|---|
| **0 — Mock** | `AdSlot` component + allowlist + mock-mode placeholder on the 3 allowed surfaces. House-ad fallback wired. | Grey "AD" placeholders visible in dev on `/`, `/jobs`, and the 404; **no placeholder visible** on forbidden routes. |
| **1 — Direct sales** | Sign **one** local sponsor at 1 500+ MZN/mo. Render their card via the Tier 2 path. No third-party JS yet. | First sponsor money in the bank. **Servers paid.** |
| **2 — Featured-job expansion** | Ship "Urgent badge" + "Homepage spotlight" as additional Stripe SKUs. | Three urgent + one spotlight sold in a month. |
| **3 — AdSense fill (optional)** | Non-personalized AdSense unit on `/jobs` only, between 8th and 9th card. House-ad fallback handles no-fill. | RPM ≥ $0.50 across 30 days. Otherwise: drop. |
| **4 — Consent + personalized** *(only if Phase 3 RPM justifies banner friction)* | Cookie banner, Consent Mode v2, personalized ads. | RPM lifts > 30 % vs Phase 3 within 30 days. |

## Phase 0 deliverable *(this PR)*

- `AD_ALLOWED_ROUTES`, `AD_DENSITY_PER_PAGE` constants in
  [`both/lib/constants.js`](../both/lib/constants.js).
- `settings.public.ads.{enabled,mock}` gates in
  [`settings-docker.json`](../settings-docker.json) +
  [`settings-example.json`](../settings-example.json).
- [`client/views/includes/adSlot.html`](../client/views/includes/adSlot.html) +
  [`adSlot.js`](../client/views/includes/adSlot.js) Blaze template,
  mock-mode only. **No `adsbygoogle.js` shipped.**
- Three placeholder mounts: `home-spotlight` on [`home.html`](../client/views/home.html),
  `feed-sponsor` on [`jobs.html`](../client/views/jobs/jobs.html),
  `empty-state` on [`notFound.html`](../client/views/includes/notFound.html).
- i18n keys (`ads.label`, `ads.mock.*`) in en/es/pt buckets of
  [`both/lib/i18n.js`](../both/lib/i18n.js).
- Playwright validation: placeholders render on allowed routes, are
  absent on forbidden routes, and suppress correctly for admin sessions.
