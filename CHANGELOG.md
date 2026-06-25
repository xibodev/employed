# Changelog

All notable changes to **Employed** are recorded here.

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
formatting and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed (FastAPI + Next.js era — current stack)

- **Quality-run fix release `employed-uat-2026-06-10`** — 28 fixes on branch
  `fix/quality-run-2026-06-10` (security, market resolution, email links,
  reCAPTCHA, admin moderation, localization, runtime config, +51 regression
  tests → 134 backend tests). **Not yet merged or deployed** — live UAT still
  runs the pre-fix `uat` @ `00aa899` build. Canonical detail:
  `docs/product/RELEASE_NOTES.md` (incl. pre-deploy gates) and
  `docs/product/FEATURE_REGISTRY.md`.
- **Docs drift sweep (2026-06-10)** — corrected stale Meteor-era and
  pre-fix claims across `README.md`, `CLAUDE.md`, `DEPLOY.md`, `PITCH.md`,
  `docs/api-reference.md`, `docs/payment-flows.md`, `docs/settings-reference.md`,
  `docs/markets-and-locales.md`, operations docs, and env examples.

---

## Historical — Meteor era (pre-May-2026 rewrite)

> Everything below this line predates the May 2026 rewrite to FastAPI +
> Next.js (`MIGRATION-PLAN.md`). File paths such as `server/*.js`,
> `client/views/*`, and `both/collections/*` refer to the retired Meteor
> codebase and no longer exist in this repo. Kept as the audit trail for
> the 1.x line.

The list is backfilled from `FIXES_PLAN.md` Tiers 1–9. Each tier shipped as a
multi-PR effort; individual ticket IDs (B*, T*, A9.*) are listed inline so
on-call can trace any single behaviour back to its rationale.

### Added

- **Quality gate fixes** — 11 code fixes applied from the automated
  quality pipeline:
  - Auth flow tests, payment registry tests, email notification tests,
    client helper tests (`tests/`)
  - Webhook signature verification stubs for M-Pesa and e-Mola
    (`server/mpesa.js`, `server/emola.js`)
  - Compound MongoDB index for featured-exclusion query
    (`both/collections/jobs.js`)

### Changed

- **Docs refresh (May 2026)** — reviewed and updated all project
  documentation for accuracy:
  - `README.md` — fixed Node version (14→18), added Testing section
    with full test inventory, refreshed upstream note, added
    Documentation index table
  - `tests/README.md` — full rewrite listing all 8 test files + E2E,
    removed stale "uncomment mocha" setup step
  - `BOOTSTRAP5_MIGRATION.md` — added status header (PR 1+2 complete),
    cross-referenced `brand/BS5-MIGRATION.md` as canonical tracker
  - `REDESIGN.md` — added archive notice (historical audit, not
    current spec)
  - `imports/styles/README.md` — updated PR 2 status to complete
  - `.github/copilot-instructions.md` — added `meteor npm test` to
    commands, added `payments.js` and `security-headers.js` to key files

### Added (documentation)

- **`docs/api-reference.md`** — REST API reference with request/response
  schemas for all HTTP endpoints (`/api/jobs`, `/healthz`, `/sitemap.xml`,
  `/feed`, `/api/me/export`, webhooks)
- **`docs/payment-flows.md`** — complete payment provider documentation
  covering Stripe, M-Pesa, e-Mola; simulator vs live mode; test MSISDNs;
  settlement lifecycle; error handling
- **`docs/markets-and-locales.md`** — end-to-end market resolution flow
  (hostname → market → country → locale → pricing → UI language)
- **`docs/settings-reference.md`** — key-by-key settings documentation
  with production requirements and env var overrides
- **`docs/operations-runbook.md`** — incident response, severity levels,
  log triage, deploy/rollback procedures, escalation matrix
- **`docs/decisions/`** — 6 Architecture Decision Records:
  - 001: Node 18 on Meteor 2
  - 002: MongoDB (not PostgreSQL)
  - 003: Meteor Accounts (not JWT)
  - 004: Bootstrap 5 phased migration
  - 005: Payment provider registry pattern
  - 006: Subdomain-based market selection

### Fixed

- `/healthz` E2E test — assertion now matches actual response shape
  (`time` not `uptime`)
- `/api/jobs` E2E test — assertion matches envelope structure
  (`{ status, data }`)
- N+1 `posterName()` in admin — publication now returns user cursor
  alongside jobs cursor
- IP hash truncation increased from 12→16 hex chars (collision
  reduction)
- Data export endpoint (`/api/me/export`) — header-based auth
  preferred over token-in-URL (deprecation warning + `Sunset` header
  added)

### Added

- **A10.0** — **Mobile-first foundations: multi-provider checkout,
  dynamic PWA manifest, service worker, install prompt, WhatsApp
  apply.** Closes the gap between "site that works on a phone" and
  "site that feels native on a phone". Five concerns landed together
  because they share the same audience (mobile users in MZ + MX) and
  the same shipping risk (any of them in isolation is a half-step).

    - **Payment provider abstraction** (`server/lib/payments.js`).
      Introduces `Payments.register({ key, name, markets, simulator,
      ui, initiate, status })` so any checkout flow can be wired in
      with a single file. Snapshots are market-scoped and serializable
      (`Payments.snapshotForMarket`) so the client receives only the
      payment options enabled for its subdomain. Existing Stripe
      flow is now an adapter (`server/payments-stripe.js`) registered
      alongside the new mobile-money providers; the legacy
      `featuredJob.checkout` method is unchanged for backwards-compat.

    - **M-Pesa + e-Mola simulators** (`server/mpesa.js`,
      `server/emola.js`). Real shortcodes/API keys are not yet
      issued, so both providers default to `simulate: true` when
      `Meteor.settings.private.mpesa.shortcode` (or the e-Mola
      partner ID) is absent. Test MSISDN ladder mirrors what the
      live providers expose:
        - M-Pesa (Vodacom MZ, 84/85 prefix): `841111111` instant ok,
          `842222222` 6s ok, `843333333` insufficient_funds,
          `844444444` user_timeout, `848888888` wrong_pin, any other
          84/85 number = 6s ok.
        - e-Mola (Movitel MZ, 86/87 prefix): same outcomes, 5s
          default delay.
      Simulators auto-settle by calling `settleSimulatedIntent` via
      `Meteor.setTimeout(Meteor.bindEnvironment(...))` so the same
      idempotent featured-extension code path that the Stripe
      webhook hits is also exercised by the simulator. When real
      shortcodes are configured the providers fall through to
      `throw new Meteor.Error('not-implemented', ...)` and the
      simulator branch is skipped — preventing accidental fake
      charges in production.

    - **`PaymentIntents` collection** (`both/collections/paymentIntents.js`).
      One row per checkout attempt with status enum (`pending`,
      `awaiting_user`, `completed`, `failed`, `cancelled`,
      `expired`). Privacy: only the last 4 digits of the MSISDN
      are stored verbatim, the full number is SHA-256-hashed with
      `private.ipSalt` for reconciliation. Indexes:
      `(providerKey, status, createdAt desc)`, `providerRef`,
      `(jobId, createdAt desc)`, `(userId, createdAt desc)`.

    - **Methods + rate limits**. `featuredJob.initiate(jobId,
      providerKey, payerMsisdn)`, `payment.status(intentId)`,
      `payment.cancel(intentId)`, `payment.providersForMarket()`,
      all owner-scoped and DDPRateLimiter-throttled (3/hr/user for
      initiate, 120/min for status polling, 12/min for cancel,
      60/min for the discovery call). Duplicate-intent guard in
      `featuredJob.initiate` returns the existing instructions for
      the same job within 5 minutes so a double-tap on "Send PIN"
      doesn't create a second pending row.

    - **`featuredCheckoutModal` UI**
      (`client/views/jobs/featuredCheckout.{html,js}` + styles in
      `client/lib/app.less`). Single Bootstrap modal walks the
      user through six stages (`pick → msisdn → awaiting →
      redirecting → success → failure`). Per-instance ReactiveVars
      so two modals can't share state; module-scope `activeHandle`
      so the modal's `hidden.bs.modal` cancels in-flight polling.
      Provider buttons use brand colours (#ED1C24 for M-Pesa, #F59E0B
      for e-Mola, #635BFF for Stripe) as left borders. The Stripe
      branch calls `window.location.assign(result.url)` (redirect
      to Stripe Checkout); the mobile-money branch polls
      `payment.status` every 3s up to a 90s ceiling.

    - **Per-market manifest endpoint** (`server/manifest.js`).
      `/manifest.json` and `/manifest.webmanifest` are served by
      `WebApp.rawConnectHandlers` with market-aware `name`,
      `short_name`, `lang`, `start_url`, `description`, `shortcuts`.
      `Vary: Host` so the CDN keeps one cached copy per subdomain.
      The static `public/manifest.json` is left in place as a
      no-network fallback. Per-market locale tags (`pt-MZ` for MZ,
      `es-MX` for MX) so the install banner picks the right language
      ahead of the in-app i18n switch.

    - **Service worker + offline page** (`public/sw.js`,
      `public/offline.html`, `client/lib/pwa.js`). Three cache
      tiers: `BUNDLE_CACHE` (cache-first, Meteor's hashed JS/CSS
      bundles are immutable), `ASSET_CACHE` (cache-first with
      stale-while-revalidate for images, fonts), `DOCUMENT_CACHE`
      (network-first with a 4s timeout so a flaky cellular link
      falls back to cache rather than spinning a blank page). Cache
      keys are versioned (`emp-bundle-v1`, etc.); bumping
      `CACHE_VERSION` in `sw.js` purges old caches on activate.
      Registration is deferred to `Meteor.startup` + page `load` so
      it never competes with the initial paint.

    - **PWA install prompt banner** (`client/views/includes/installPrompt.{html,js}`).
      `beforeinstallprompt` is captured and held until the banner
      template fires it on user gesture; banner only shows on
      mobile viewports (`@media (max-width: 767px)`), only after
      `appinstalled` hasn't fired, and only after the user's last
      dismissal is older than 30 days (or 7 days if they dismissed
      the OS-native prompt). State persists in `localStorage`.

    - **WhatsApp apply** (`both/collections/jobs.js`,
      `client/views/jobs/jobForms.html`, `client/views/jobs/job.{html,js}`).
      New optional `applyWhatsApp` field on every job. When set, a
      green "Apply on WhatsApp" CTA renders in the job detail
      sidebar + the mobile sticky bar, deep-linking to
      `wa.me/<digits>?text=<localised template>`. Localised
      prefilled message ("Hi! I'm interested in the {{title}} role
      at {{company}}…") in en/es/pt. Phone validation is permissive
      (any common E.164-ish format) in the schema; the client
      strips non-digits before constructing the `wa.me` URL.

    - **Meteor 3 audit doc** (`docs/meteor-3-package-audit.md`).
      Triage of the Atmosphere package set for the Meteor 3
      upgrade. Identifies which packages have async/promise-based
      replacements, which are abandoned, and which still need
      ownership before the upgrade can ship.

    - **Perf budget scaffolding** (`perf-budget.json`,
      `scripts/check-bundle-size.mjs`, `scripts/lighthouse-mobile.mjs`,
      `package.json` scripts `perf:*`). Hard/soft caps on gzipped
      JS/CSS/HTML bundle size, a Lighthouse runner with a slow-4G +
      4× CPU mobile preset, and report artefacts under
      `.lighthouse/`. Doesn't gate CI yet — this is the first
      planking before A10.1 wires it into the pipeline.

    - **Settings docs** (`settings-example.json`, `settings-docker.json`).
      `private.mpesa` and `private.emola` blocks added with
      simulator-on defaults and a `_comment_about_simulate` block
      explaining the test MSISDN ladder. The Docker compose
      settings ship with `simulate: true` so a fresh `docker
      compose up --build` boot has a working end-to-end checkout
      flow without external dependencies.

- **A9.36** — **Random featured strip + paginated jobs feed with
  interleaved ads.** After A9.35 shipped, the seeded `/jobs` page
  rendered every paid listing inline with the recent jobs (27
  amber-bordered tiles competing for attention) and dumped all 297
  active jobs into a single scrolling grid. This release caps the
  paid surface to exactly one row of randomly-sampled featured jobs
  and adds proper pagination with ad interleaving on the long feed.

    - **Featured strip** — one grid row (3 tiles at desktop), randomly
      drawn from currently-active featured jobs that are within the
      90-day window. The strip renders above the filter bar on `/jobs`
      and above the recent feed on home. Visual chrome: amber pill
      "Featured" badge + a one-line subtitle ("A fresh pick of paid
      listings.") so the row reads as paid territory without
      overpowering the rest of the page. New publication
      `featuredJobs(marketKey, size)` in `server/publications.js`
      uses MongoDB `$sample` via `Jobs.rawCollection().aggregate(...)`
      and ships the docs over the existing `jobs` MiniMongo
      collection (so `Jobs.helpers({ featured(), path(), slug() })`
      automatically apply). `size` defaults to 3 and is clamped to
      `1..12`. The sample stabilises for the SubsManager cache
      lifetime (≈5 min), then re-rolls — "feels alive" without
      per-navigation churn.

    - **Pagination on `/jobs`** — page sizes 12 / 24 / 48 selectable
      via a `<select>` next to the prev/next buttons. New helpers in
      `client/views/jobs/jobs.js`: `pageSizeOptions`, `currentPageSize`,
      `totalCount`, `totalPages`, `currentPageLabel`, `pageFromLabel`,
      `pageToLabel`, `prevDisabled`, `nextDisabled`. Pagination state
      lives in `JobsFilter` (the same `ReactiveDict`-backed snapshot
      that powers the search / type / remote filters) so any filter
      change auto-resets to page 1 via `JobsFilter.resetPage()`.
      `jobs.html` adds a `<nav class="jobs-pagination">` with a left-side
      range summary ("Showing 1–12 of 212") and a right-side controls
      group (per-page select + Previous / "Page X of Y" / Next). The
      `jobs` publication now accepts `page` + `pageSize` (allowlisted
      server-side to `[12, 24, 48]`) and applies `skip` + `limit` +
      `sort: { createdAt: -1 }`. The client-side `Jobs.find()` mirrors
      the same `skip` + `limit` so SubsManager's 5-minute cache
      doesn't leak the previous page's docs into the current grid.

    - **`jobs.count` method + rate limit** — `server/methods.js` ships
      a new Meteor method that takes the same filters bag as the
      `jobs` pub and returns the total matching count. Throttled to
      120 calls/min/connection via `DDPRateLimiter` in
      `server/rate-limits.js`. `Template.jobs.onCreated` runs an
      autorun that calls `jobs.count` whenever the filter fingerprint
      (everything except `page`) changes, storing the result in a
      module-level `ReactiveVar` so pagination labels stay accurate
      across page changes without re-querying.

    - **Inline ad rows every 4 tiles** — the main grid is now built by
      a `jobsWithAds` helper that fetches the current page slice, then
      pushes an ad marker after every 12th tile (= 4 rows × 3 cols at
      desktop). Math by page size: 12/page → 1 ad (trailing),
      24/page → 2 ads, 48/page → 4 ads. The ad row uses a new
      `.job-ad-inline` tile that spans the full grid width via
      `grid-column: ~"1 / -1"` (the `~""` escape is required because
      the LESS compiler otherwise evaluates `1 / -1` as arithmetic
      and emits `-1`, collapsing the span to a single column and
      forcing an extra implicit grid column).

    - **`jobs` publication excludes active-featured docs** so the
      featured strip pub is the single source of truth for those
      tiles. Filter is
      `$or: [{ featuredThrough: { $exists: false } }, { featuredThrough: { $lt: new Date() } }]`,
      and the query-text path promotes both `$or` clauses into
      `$and: [{ $or: ... }, { $or: ... }]` so featured-exclusion +
      title/company/location regex compose correctly. The `jobs.count`
      method applies the same selector for parity.

    - **Router wiring** — both the home route (`/`) and `/jobs` route
      in `router.js` subscribe to `featuredJobs(currentMarketKey(), 3)`
      and expose a `featuredJobs` cursor (limited to 3 docs to match
      the publication). The home `data` continues to pass `jobs` as
      the cursor for the recent feed; `jobsRecent.js` now exposes
      `hasFeatured` and `hasRecent` booleans alongside `hasJobs` so
      the template renders each strip independently and only falls
      back to the empty state when both are empty.

    - **i18n** — 8 new keys × 3 locales placed adjacent to
      `jobs.salary.per.year` in each locale block:
      `jobs.featured_strip_label`, `jobs.featured_strip_subtitle`,
      `jobs.pagination.page_size_label`, `jobs.pagination.previous`,
      `jobs.pagination.next`, `jobs.pagination.page_of`,
      `jobs.pagination.showing`, `jobs.ad_inline.label`. Spanish:
      Destacados / Anterior / Siguiente / Página X de Y / Mostrando
      1–12 de 212 / Por página. Portuguese: Em destaque / Anterior /
      Seguinte / Página X de Y / A mostrar 1–12 de 212 / Por página.

    - **Styles** in `client/lib/app.less` — new blocks for
      `.featured-strip`, `.featured-strip-heading`, `.featured-strip-badge`
      (amber pill `#FEF3C7` / `#92400E`), `.featured-strip-subtitle`,
      `.job-ad-inline` (full-row span, 4px vertical margin),
      `.jobs-pagination` (flex layout with a 560px breakpoint that
      stacks the range summary below the controls), `.pagination-summary`,
      `.pagination-controls`, `.pagination-page-size`,
      `.pagination-page-size-label`, `.pagination-buttons`,
      `.pagination-page-of`.

- **A9.35** — **Tile-card job listings**. Replaces the single-job-per-row
  layout on `/jobs`, the home "Recent jobs" feed, and the empty-state
  with a responsive CSS Grid of tile cards (1 column on mobile, 2 at
  ≥768px, 3 at ≥1100px; 14px gap, 200px min height). The redesign was
  driven by the A9.34 seed: with 297 active jobs on screen, the old
  full-width row layout buried the catalogue under one-line previews
  and made browsing feel sparse. Each tile now surfaces the avatar,
  title (2-line clamp), company + location, jobtype + remote + featured
  badges, an indigo salary chip (`MZN 28,000 – 71,000 / mês`,
  `MXN 13,000 – 28,000 / mes`), a 2-line description excerpt, and the
  posted date pinned to the footer. Featured tiles get an amber top
  border + cream tint so paid listings stand out without overwhelming.

    - **New helpers** in `client/helpers.js`:
        - `descExcerpt` — first paragraph only (splits on `\n\s*\n`),
          whitespace-normalised, truncated to ≤160 chars at the last
          word boundary, ellipsis-appended only when actually clipped.
          Pure function, safe in Blaze reactive contexts.
        - `salaryLabel` — formats `currency min [– max] [/ period]`
          where the period suffix resolves through i18n
          (`jobs.salary.per.{hour,day,week,month,year}`) with graceful
          fallback to the raw value if a custom period sneaks in.

    - **New i18n keys** in `both/lib/i18n.js` for all 3 locales:
        - `jobs.salary.per.hour|day|week|month|year` —
          en: hour/day/week/month/year, es: hora/día/semana/mes/año,
          pt: hora/dia/semana/mês/ano. Placed in each locale block
          next to the existing `jobs.featured_until` key so future
          maintainers see them clustered with related listing strings.

    - **Templates** in `client/views/jobs/`:
        - `jobSmall.html` rewritten — the root element is now
          `<a href="{{pathFor 'job'}}" class="jobSmall job-tile {{#if featured}}featured{{/if}}">`,
          making the entire tile clickable (matches mobile-first
          expectations; the old `.btn` row had a click target the size
          of the title only). Sub-structure: `.job-tile-header`
          (avatar + heading) → `.job-badges` → conditional `.job-salary`
          → conditional `.job-excerpt` → `.job-tile-footer` (right-aligned
          date with a dashed top divider).
        - `jobs.html` wraps `{{#each jobs}}` in a `.job-grid` div, gated
          on `{{#if jobCount}}` so the existing empty-state SVG + CTA +
          `adSlot position="empty-state"` keep their previous look.
          Footer `adSlot position="feed-sponsor"` preserved.
        - `jobsRecent.html` rewritten — combines featured + recent into
          the same `.job-grid` (was two separate `{{#each}}` loops with
          divider markup between them); empty state is a single muted
          clock-icon row instead of two parallel empty messages.
        - `jobsRecent.js` — new `hasJobs` template helper that returns
          true when either cursor has count > 0. Necessary because Mongo
          cursors are always truthy in Blaze `{{#if}}`, so the previous
          `{{#unless jobs}}` empty-state path was unreachable.

    - **CSS** in `client/lib/app.less` (with `client/views/jobs/jobSmall.less`
      cleaned of the conflicting `.jobSmall.featured { background: #ffc }`
      legacy rule):
        - `.job-avatar` lifted out of the old `.jobSmall { }` nest to
          top-level (44×44, 10px radius, 8-bucket deterministic colour
          palette) so both tile and row variants share it.
        - `.job-grid` — CSS Grid 1/2/3 cols at 768/1100px, 14px gap,
          20px bottom margin.
        - `.jobSmall.job-tile` — full tile chrome: flex column,
          1px `#E5E7EB` border (→ `#C7D2FE` on hover), 10px radius,
          16px padding, `min-height: 200px`, hover lift
          `translateY(-2px)` + `0 6px 18px rgba(0,0,0,0.08)`, anchor
          colour/decoration reset. Children: header flex row, title
          2-line `-webkit-line-clamp`, badges flex wrap, salary chip
          (`#EEF2FF` bg / `#3730A3` fg, pill), excerpt 2-line clamp in
          gray-600, footer `margin-top: auto` pinning date to bottom.
        - `.jobSmall.my-job-row { }` block added back at the bottom —
          restores the legacy row primitives (`.job-card-inner`,
          `.job-main`, `.job-title-link` single-line ellipsis, `.job-meta`,
          `&.featured` left amber border) so the `myJobs` dashboard,
          which still uses the row layout for its denser admin-style
          table, is **not** affected by this redesign.

    - **Publications** in `server/publications.js` — `homeJobs`,
      `featuredJobs`, and `jobs` now ship `description`, `salaryMin`,
      `salaryMax`, `salaryCurrency`, and `salaryPeriod` in their
      `fields:` projection so the excerpt + salary chip have data to
      render. Wire-size impact: about +150 KB per fully-paginated
      100-job page (description fields are short; salary fields are
      tiny). Acceptable for now given the tile UX win; future
      optimisation could trim `description` to a server-computed
      excerpt at publish time.

    - **Validation** — Playwright DOM checks on `mz.lvh.me:3001/jobs`
      with the seeded stack: `{ tiles: 100, excerpts: 100, salaries: 57,
      featured: 27, gridCols: 2-or-3 }`. Manual screenshot review at
      390 / 768 / 1280 px on both MZ and MX confirms the grid reflow
      and Portuguese/Spanish salary period suffixes. Tile-as-anchor
      navigation verified by clicking the first MX tile and landing on
      the matching job detail page.

- **A9.34** — **Dev seed script for local demo data**. Adds
  `server/dev-seed.js`, a triple-gated startup hook
  (`Meteor.isDevelopment` + `private.devSeed.enabled` + version
  marker) that idempotently populates a fresh local stack with
  realistic-looking data so the UI demonstrates "what this looks
  like in real life" on first boot. Defaults: **2 admins, 100
  employer accounts, 400 jobs** spread roughly 80/20 across MZ/MX
  with weighted distributions over status (~72% active, 12% pending,
  4% flagged, 8% inactive, 4% filled), job type (Full Time-heavy),
  salary bands (~65% include a salary), remote flag (~18%), and
  featured boost (~12% of active have a current `featuredThrough`,
  ~5% have a lapsed one). `createdAt` is spread evenly across the
  last 85 days so the home "Recent jobs" feed shows variety and the
  90-day expiry cron has something near its boundary to chew on.
  Bulk-inserts via `rawCollection().insertMany` for speed (~7s for
  400 jobs + 100 users) and bypasses the schema's `userId` autoValue
  cleanly. A custom `_devSeed` marker collection tracks what was
  inserted; `private.devSeed.reset = true` wipes only those IDs and
  re-seeds, leaving any hand-created data untouched. Seeded users
  share a password (`seedpass123` by default) and use predictable
  emails (`seed.admin.N@employed.local`, `seed.user.NNN@employed.local`)
  so they're trivially recognisable in the admin queue. Disabled by
  default in `settings-example.json`; on for the docker UAT stack.
- **A9.33** — **Ads Phase 0 (mock-mode AdSlot)**. Lands the first ad
  surface in a deliberately reversible shape: a single Blaze component
  (`adSlot`) that today renders only a styled placeholder ("Your ad
  here / sponsor this slot") and ships with no AdSense JS, no
  third-party network calls, and no consent UI. Mounted on exactly
  three pages — home (`home-spotlight`, below recent jobs), browse
  (`feed-sponsor`, results footer), and 404 (`empty-state`). The
  strategy that drove the shape — why Employed does **not** copy
  SeloPro's stack, why MZ AdSense fill is unreliable, and the four
  upgrade phases (mock → direct sponsors → AdSense → in-feed) — is
  committed under `docs/ads-strategy.md`.

    - **New files**
        - `docs/ads-strategy.md` — full strategy + surface map +
          phasing + kill rules.
        - `client/views/includes/adSlot.{html,js,less}` — the gated
          component. `shouldRender` checks five gates in order: master
          kill switch (`Meteor.settings.public.ads.enabled`),
          **template-ancestry allowlist** (`AD_ALLOWED_TEMPLATES`),
          admin auto-suppress, paying-employer auto-suppress (any
          active `featuredThrough`), and explicit call-site `suppress`
          prop. Mock-mode placeholder uses the A9.30 brand palette
          (cream + indigo + amber) with a dashed border so reviewers
          can spot every mount at a glance.
        - `Meteor.publish('mySponsorState')` in `server/publications.js`
          — a tiny per-user subscription (`_id`, `userId`,
          `featuredThrough`) that the suppress check reads from
          MiniMongo. Required because `homeJobs`/`featuredJobs` strip
          `userId`, so the suppress logic had no way to scope by owner
          before this. Subscribed always-on from `client/autorun.js`
          whenever there's a `Meteor.userId()`.

    - **Why template-ancestry, not route name** — iron-router's
      `dataNotFound` plugin renders the `notFound` template while
      leaving `Router.current().route.getName()` set to the **original**
      route (e.g. `/jobs/<bad-id>` still reports route `job`). Route
      allowlisting would have either missed real 404 hits or leaked
      ads onto job detail pages. Walking the Blaze view tree gives us
      exactly what's mounted in the DOM.

    - **Changed files**
        - `both/lib/constants.js` — `AD_ALLOWED_TEMPLATES` +
          `AD_DENSITY_PER_PAGE`.
        - `both/lib/i18n.js` — `ads.label`, `ads.mock.{title,
          subtitle, cta}` across en/es/pt.
        - `settings-docker.json` — `public.ads = { enabled: true,
          mock: true }` (UAT default).
        - `settings-example.json` — `public.ads = { enabled: false,
          mock: true }` (production default; explicit opt-in).
        - `client/views/home.html` — `{{> adSlot position="home-spotlight"}}`.
        - `client/views/jobs/jobs.html` — `{{> adSlot
          position="feed-sponsor"}}` (gated on `jobCount` so the slot
          doesn't double up alongside the empty-state mock), plus
          `{{> adSlot position="empty-state"}}` inside the
          empty-state branch.
        - `client/views/includes/notFound.html` — `{{> adSlot
          position="empty-state"}}`.
        - `client/autorun.js` — always-on `mySponsorState` subscribe.

    - **Validation matrix** (Playwright against `mz.lvh.me:3001`):
      home → `home-spotlight` rendered; `/jobs` with results →
      `feed-sponsor` only; `/jobs` empty → `empty-state` only (no
      double-up); `/jobs/<bad-id>` → 404 template + `empty-state`
      mock; real job detail (`/jobs/uat-seed-001`), `/post-a-job`,
      `/sign-in` → zero slots; admin (`admin@example.test`) signed
      in on `/` → zero slots; signed-in user with an active
      `featuredThrough` job → zero slots; sign-in bounce flow
      (`/myjobs` → `/sign-in`) still works.

    - **Not in scope of this PR** — no AdSense `<ins>` tag, no
      consent banner, no in-feed cadence on `/jobs`, no rate-limited
      dwell-time tracking, no admin UI for direct sponsors. Those
      land in Phases 1–4. See `docs/ads-strategy.md` § "Phasing".

- **A9.32** — Bootstrap 5 migration **PR 2 — useraccounts replacement**.
  Removes the abandoned `useraccounts:*` packages and replaces them with
  hand-rolled Blaze templates that talk to `Accounts.*` directly. No
  visual change yet (still BS3 markup); PR 3 will re-skin them under
  BS5. Net effect: the auth surface is now ours to evolve, the
  `forbidClientAccountCreation: true` gate is gone, and there are no
  more transitive deps on packages that haven't shipped since 2018.

    - **Removed packages** (in `.meteor/packages`, commented out with
      A9.32 explanations so the next operator can see *why*):
      `useraccounts:bootstrap`, `useraccounts:iron-routing`, and the
      transitive `useraccounts:core` (auto-removed by Meteor's resolver).
    - **New** `client/views/account/auth.html` — five Blaze templates
      (`signIn`, `signUp`, `forgotPwd`, `resetPwd`, `verifyEmail`) using
      the existing BS3 markup, wired to a single `auth.js` handler file.
    - **New** `client/views/account/auth.js` — submit handlers that call
      `Meteor.loginWithPassword`, `Accounts.createUser`,
      `Accounts.forgotPassword`, `Accounts.resetPassword`, and
      `Accounts.verifyEmail` directly. Localised error messages flow
      through the existing `t()` helper.
    - **New** `.meteorignore` — excludes `brand/`, `design/`, `scripts/`
      from Meteor's templating-compiler. Those folders hold standalone
      `.html` artefacts (preview pages, logo concept galleries, branded
      email mock-ups) that include their own `<!DOCTYPE html>`. Without
      this file the compiler crashes at boot trying to parse them as
      Blaze fragments.
    - **Updated** `server/accounts.js` — adds
      `Accounts.config({ sendVerificationEmail: true })` and
      `Accounts.urls.{verifyEmail,resetPassword}` overrides that emit
      clean tokenised URLs (`/verify-email/:token`, `/reset-password/:token`).
    - **Updated** `router.js` — adds the five auth routes, plus an
      inlined `ensureSignedIn` hook (the original was provided by the
      now-removed `useraccounts:iron-routing` package) that captures
      the intended URL in `Session.postSignInRoute` before redirecting
      anonymous users to `/sign-in`. The `signIn`/`signUp` route guards
      read `Meteor.userId()` via `Tracker.nonreactive` so iron-router
      doesn't re-fire them on login — that race was sending users to
      `/` instead of their pre-login destination. The form callbacks
      in `auth.js` own the post-login redirect via `redirectAfterAuth()`.
    - **Stripped** `both/accounts.js` to a comment-only stub pointing to
      the new files; removes the dead `AccountsTemplates.configure` /
      `addField` / `redirectAfterAuth` block.
    - **Updated** `.eslintrc.json` — removed the `AccountsTemplates`
      global.
    - **Verified** end-to-end via Playwright UAT against the mz market:
      sign-in (`user@example.test`), sign-up (auto-login + verification
      email delivered to MailHog), forgot password (reset email delivered
      to MailHog), and the `/myjobs` → `/sign-in` → submit → `/myjobs`
      round-trip with `postSignInRoute` correctly preserved across the
      redirect.

- **A9.31** — Bootstrap 5 migration **PR 1 — Foundation** (partial).
  No runtime change; lays the groundwork so PR 2 (useraccounts
  rewrite) and PR 3 (template sweep) can be picked up turn-key:
    - `bootstrap@5.3.3` + `@popperjs/core@2.11.8` installed as
      **devDependencies**. Excluded from the prod runtime by the
      multi-stage Docker build (`Dockerfile.prod` Stage 1 discards
      builder-layer `node_modules`).
    - `imports/styles/_app-bs5.scss` — BS5 SCSS variable overrides
      mapped to the brand palette (indigo / amber / ink / cream),
      typography (Inter / Montserrat), and 8/6/12px border radii.
      Exposes the brand palette as CSS custom properties
      (`--brand-indigo` etc.) for any future React / web-component
      surfaces.
    - `imports/styles/_useraccounts-bs5.scss` — scaffold for the
      hand-rolled sign-in / sign-up / password-reset templates that
      will replace `useraccounts:bootstrap` in PR 2. Includes the
      full PR 2 checklist as a code comment so the next session
      can pick it up cold.
    - `imports/styles/README.md` — step-by-step activation
      cheatsheet for PR 2 + PR 3. Explains why the files are staged
      under `imports/` (lazy-load zone) rather than `client/`
      (would auto-compile and clash with mounted BS3 styles).
    - `brand/BS5-MIGRATION.md` — status flipped from `DEFERRED` to
      `PR 1 in progress`, with explicit progress checklists for
      each PR.

- **A9.30** — Full visual rebrand from the legacy red `#b73737` mark to the
  new Employed identity (indigo `#4F46E5` + amber `#F59E0B` + dark `#27272B`).
  Shipped as one PR with two concerns kept separate:
    1. **Brand kit** under `brand/` — source-of-truth folder with
       documentation (colors, typography, voice, usage), logos (mark,
       horizontal lockups, dark variants, monochrome, favicon),
       trust seals (featured / verified / unverified), social media
       templates (OG card, Facebook cover, Twitter banner, LinkedIn
       banner, Instagram post + story), merch templates (t-shirt,
       sticker, business card), email templates (signature, header),
       a self-contained `preview.html`, and a separate
       `BS5-MIGRATION.md` documenting the deferred Bootstrap 3 → 5
       work.
    2. **In-app surfaces** — `public/images/logo.svg` + `favicon.svg`
       redrawn; `public/images/og-card.svg` added; `manifest.json`
       and `client/views/main.html` theme_color flipped to indigo.
       New brand pills for Featured / Verified / Unverified replace
       BS3 `.label .label-*` chrome. Animated logo spinner replaces
       FontAwesome `fa-spinner`. Custom 404 closed-door illustration
       replaces `fa-frown-o`. Empty-state briefcase + magnifier
       composition replaces `fa-search`. Reply default avatar swapped
       from red person silhouette to indigo+amber SVG. Designed
       1200×630 OG card wired through `mdg:seo` defaults. Every
       transactional email (`server/methods.js` × 4 sites,
       `server/accounts.js` verifyEmail + resetPassword) wrapped in
       branded HTML chrome with dark header + logo + amber-accented
       wordmark, via a single `brandedEmail()` helper in
       `server/lib/helpers.js`.
- **A9.30-DEFER-BS5** — Bootstrap 3 → 5 migration documented in
  `brand/BS5-MIGRATION.md` but **not** executed in this PR. Reason: the
  Meteor 2 ecosystem has no clean `nemo64:bootstrap` BS5 successor and
  `useraccounts:bootstrap` would need a full hand-rolled replacement.
  Splitting these concerns keeps the rebrand reviewable on its own.
- **A9.30-PNG-REGEN** — `scripts/regen-brand-pngs.js` +
  `@resvg/resvg-js` devDependency + `npm run regen-brand-pngs` script.
  Rasterises every brand SVG to the exact PNG fallback the app + PWA
  manifest reference, with byte-equality skip so unchanged files don't
  bloat git history. All ten checked-in PNGs (`favicon.png`,
  `favicon-16/32`, `apple-touch-icon`, `icon-192/512`,
  `maskable-icon-192/512`, `og-card`, `avatar`) are now in lockstep
  with the new indigo mark.

- **A9.13** — `Dockerfile.prod` (multi-stage build), `.meteor/galaxy.json`
  manifest, README "Production Deployment" section covering Docker, Galaxy,
  settings, backup/restore, rollback, and post-deploy smoke tests.
- **A9.14** — Sentry server (`server/error-reporter.js`) and browser
  (`client/lib/sentry.js`) reporters. No-op without `private.sentry.dsn` /
  `public.sentry.dsn` populated. Wraps every `Meteor.methods` and
  `Meteor.publish` registration so handler exceptions are captured with
  hashed userId, method name, and argument shape (never values).
- **A9.3** — User-facing account page (`/account`) with self-serve data
  export and 30-day delayed deletion. Server cron sweep deletes accounts
  past `deletionScheduledFor`. `/api/me/export` returns a JSON snapshot
  of the user document and owned jobs.
- **A9.16** — This `CHANGELOG.md`, plus `package.json` version bump to
  `1.1.0`.
- **A9.20** — All `Jobs` collection field labels routed through the in-repo
  i18n module via a boot-safe `i18nLabel()` wrapper.
- **A9.23** — Per-locale `<link rel="alternate" hreflang="…">` and
  `<link rel="canonical">` tags, plus schema.org `JobPosting` JSON-LD on
  every job page.
- **A9.24** — Job-list search box, employment-type select, and remote-only
  toggle. Filters are validated server-side and applied to the `jobs`
  publication.
- **A9.25** — Optional `salaryMin` / `salaryMax` / `salaryCurrency` /
  `salaryPeriod` fields on jobs. Surfaced in JSON-LD `baseSalary` when set.
- **A9.26** — Community report flow: "Report this job" button on the job
  detail page, a `JobReports` collection, server-side `jobReports.create`
  and `jobReports.resolve` methods, an admin queue rendered inline on
  `/admin/jobs`, and full i18n coverage.
- **A9.31** — Mobile-friendly Summernote toolbar with viewport-aware
  option picker.
- **A9.36** — `Intl.DateTimeFormat` used by `formatDate` so dates honour
  the active locale instead of always rendering in `M/D/YY`.
- **A9.38** — `bulkWrite` (ordered: false) migration v7 with per-doc
  `migrationV7Done` flag for idempotency.

### Changed

- **A9.37** — `Jobs.description` max length raised from 20 000 to 50 000
  characters to match what the editor can already produce.
- **A9.41** — `eslint-plugin-security` recommended config enabled.
- **U11.1** — New brand mark: a polished red rounded-square "E" SVG used
  as both the navbar logo and the SVG favicon
  ([public/images/logo.svg](public/images/logo.svg),
  [public/images/favicon.svg](public/images/favicon.svg)). Replaces the
  flat unrounded mark. PNG variants under `public/images/` are unchanged
  and remain a visually acceptable fallback for browsers without SVG
  favicon support; regenerate them from the new SVG when convenient for
  pixel-perfect consistency.
- **U11.2** — Header navbar now uses a lockup of the new brand mark + the
  market-specific site name ([client/views/includes/header.html](client/views/includes/header.html),
  [client/views/includes/header.less](client/views/includes/header.less)).

### Removed

- **U11.3** — Footer links to GitHub and Galaxy hosting removed
  ([client/views/includes/footer.html](client/views/includes/footer.html)).
  The footer top row now displays a small brand lockup instead.
  Translation keys `footer.github` and `footer.hosted_on_galaxy` deleted
  from all three locales in [both/lib/i18n.js](both/lib/i18n.js).
- **U11.4** — `LICENSE.txt` (stale 2015 upstream MIT) and
  `wework.sublime-project` (Sublime Text project from upstream) deleted
  from the repo. Canonical `LICENSE` (2019 Abdul Gafar Manuel Meque)
  remains. `FIXES_PLAN.md` moved out of the repo root to
  [docs/archive/FIXES_PLAN.md](docs/archive/FIXES_PLAN.md) as a
  historical record now that all tiers are shipped.

### Fixed

- **U10.1** — Job posting wizard step 1 now advances correctly. The
  previous gating logic relied on `SimpleSchema#validate(partial, { keys })`,
  which `aldeed:simple-schema@1.5.4` silently ignores: it validates the
  partial doc against the full schema and always reports the unfilled
  required keys, so the gate never opened. Replaced with a per-key
  `validateOne` loop after `resetValidation()`. Symptom for end users
  was an unresponsive "Next" button with no feedback.
- **U10.2** — Job posting wizard step 2 now advances when the description
  editor is populated. **Real production bug**: `mpowaga:autoform-summernote`
  strips the `name` attribute off the underlying `<textarea>` when it
  mounts the Summernote editor, so the wizard's
  `[name="description"]` selector found zero elements and the field
  was always treated as missing. Special-cased the description field to
  read from `.note-editable` (desktop summernote) with a fallback to
  the unaltered mobile `textarea[name="description"]`. Desktop posters
  literally could not get past step 2 before this fix.
- **U10.3** — `tests/e2e/journeys.spec.js` `waitForEmailSubject` helper
  now decodes RFC 2047 Q/B encoded-word MIME segments before matching,
  so predicates can be written in natural English even when Meteor's
  `Email.send` Q-encodes the subject (e.g. when it contains an em-dash).

### Removed

- **A9.22** — `client/views/profiles/profileForms.html` (and its now-empty
  parent directory) deleted; the developer profile feature is no longer
  surfaced anywhere.

### Documentation

- **A9.27**, **A9.28**, **A9.33** — Documentation-only entries describing
  the connection-banner package age, Bootstrap 3 / Font Awesome 4 EOL
  status, and the WCAG AA contrast audit plan. See the deviation notes
  inside `FIXES_PLAN.md`.

### Operator validation TODOs

These items ship in code/config form but require an operator action to
fully complete:

- **A9.1** — Run the existing test suite (`meteor npm test`) and verify
  startup-checks reject placeholder settings.
- **A9.11** — `meteor build` end-to-end on the Node 18 image.
- **A9.13** — Docker build + Galaxy deploy on a staging URL.
- **A9.14** — `meteor npm install` then populate the Sentry DSN; throw a
  deliberate `Meteor.Error('sentry-test')` to confirm the event arrives.
- **A9.3** — Cron-driven account deletion runs every 6h in
  `server/cron.js`; verify the cancel flow first and take a Mongo backup
  before enabling on production. The block can be commented out until
  validated.
- **A9.29** — Binary favicon assets still need to be generated.
- **A9.33** — Manual WCAG AA contrast pass with axe / Lighthouse.
- **A9.41** — `meteor npm run lint` must pass after the dev-dependency
  install.

## [1.0.x] — pre-1.1, shipped tiers

The 1.0.x line covers Tiers 1–8 from `FIXES_PLAN.md`. They shipped as
multiple PRs and are summarised here so the on-call can find them quickly.

### Tier 1 — Critical / correctness (B1.\*)

- Email verification gates on protected actions (post-job, edit-job).
- Server-authoritative `slug()` on `Jobs` so the URL can't drift.
- Featured-job Stripe flow checked end-to-end (success URL idempotency,
  webhook hardening, refund-on-error).
- reCAPTCHA v3 enforced server-side, score threshold from settings, dev
  bypass gated on `Meteor.isDevelopment`.

### Tier 2 — Security (B2.\*)

- BrowserPolicy CSP (`server/security-headers.js`) with explicit Stripe,
  reCAPTCHA, Avatar provider, and own-origin allowances.
- `helmet`-equivalent headers (HSTS, X-Frame, X-Content-Type-Options,
  Referrer-Policy).
- DDPRateLimiter (`server/rate-limits.js`) on every public method.
- SimpleSchema-validated `Match` patterns on every public method/pub.
- IP and identifier hashing helper (`hashIdentifier`) so structured logs
  never carry raw PII.

### Tier 3 — Payments (B3.\*)

- Stripe webhook signature verification.
- Featured-job charge history retained on the Job doc.
- Successful-payment idempotency keyed by Stripe session id.

### Tier 4 — Moderation UX / admin (B3.\*)

- Status-tab driven admin job list (`/admin/jobs`).
- Bulk status set with reason field (B3.8).
- Admin grant/revoke flow keyed off Mongo `_id` (B3.7).

### Tier 5 — Hygiene / dead code

- Removed legacy developer-directory routes from the public navigation.
- Consolidated the dead Astronomer / Kadira analytics keys (kept in
  settings for backwards compatibility but unused).

### Tier 6 — Platform / long-term

- Pinned Meteor 2.7.1, MongoDB 5 (compose pin), Node 18 LTS (A9.11).
- Replaced inline favicon CSS with `public/` assets.
- Documented the multi-market subdomain model in `CLAUDE.md`.

### Tier 7 — Post-Tier-6 internal sweep

- `server/healthz.js` returns `{ ok: true, mongo, version, uptime }`.
- `server/api.js` (Restivus) `/api/jobs` envelope with pagination.
- Sitemap (`server/sitemap.js`) and RSS (`server/rss.js`) feeds emit per
  active market.

### Tier 8 — i18n + a11y + SEO (internal sweep)

- In-repo i18n module at `both/lib/i18n.js` (`en`/`es`/`pt`) — no npm
  dep, BCP-47 fallback, header dropdown switcher persisted to
  `localStorage`.
- `mdg:seo` per-route titles / descriptions / og: tags.
- Custom AppDialog system replacing native `confirm()` / `prompt()` /
  `alert()` everywhere.
- Aria labels on every interactive control, including the moderation
  queue and the Summernote toolbars.

[Unreleased]: https://github.com/xibodev/employed/compare/v1.0.x...HEAD
[1.0.x]: https://github.com/xibodev/employed/releases/tag/v1.0.x
