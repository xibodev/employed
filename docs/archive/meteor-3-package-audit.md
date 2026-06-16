# Meteor 3 upgrade — package audit

> **OBSOLETE (2026-06-10):** the Meteor stack was retired by the May 2026
> rewrite to FastAPI + Next.js (`MIGRATION-PLAN.md`); the Meteor 3 upgrade
> will never happen. Kept as historical reference only.

> Triage table for `upgrade/meteor-3` branch (B24). Inputs: `.meteor/packages`,
> `package.json`, and a survey of upstream maintenance status as of
> May 2026. **Do not** start the upgrade until every ❌ has a confirmed
> replacement landed on a prep branch.

## Status legend

- ✅ **Compatible** — package has a published Meteor 3 build or no
  Fibers / async-API dependencies; the upgrade should be a no-op.
- ⚠️ **Needs verification** — package builds against Meteor 3 in our
  past audits but exposes APIs (sync wrappers, custom server hooks)
  that may surface drift. Smoke-test in a throwaway project before the
  real branch lands.
- ❌ **Blocker** — package is unmaintained or known-incompatible.
  Replace with the suggested alternative *before* `meteor update --release 3.x`.
- 🗑️ **Drop** — package is already disabled in this codebase or no
  longer needed; remove from `.meteor/packages` as part of the prep PR.

## Audit

| Package | Current | Status | Notes / replacement plan |
|---|---|---|---|
| `meteor-base` | 1.5.1 | ✅ | Ships with the platform release. |
| `mobile-experience` | 1.1.0 | ✅ | Required for Capacitor wrap in Phase 5. Keep. |
| `mongo` | 1.14.6 | ⚠️ | Meteor 3 ships a newer Mongo driver. All `Jobs.rawCollection().aggregate(...)` calls in `server/publications.js` (`featuredJobs` $sample), `server/dev-accounts.js` (seed), and similar sites become natively `await`-able — drop the `Promise.await(...)` wrappers as part of the Fibers removal sweep. |
| `blaze-html-templates` | 1.0.4 | ✅ | Blaze has an official Meteor 3 release. Templates do not change. |
| `session` | 1.2.0 | ✅ | |
| `tracker` | 1.2.0 | ✅ | |
| `reactive-var` | 1.0.11 | ✅ | |
| `random` | 1.2.0 | ✅ | |
| `ejson` | 1.1.2 | ✅ | |
| `check` | 1.3.1 | ✅ | |
| `logging` | 1.3.1 | ✅ | |
| `reload` | 1.3.1 | ✅ | |
| `ecmascript` | (latest) | ✅ | |
| `dynamic-import` | 0.7.2 | ✅ | Needed for the code-split chunks the PWA shell uses. |
| `shell-server` | 0.5.0 | ✅ | |
| `underscore` | 1.0.10 | ✅ | Used by templates; consider replacing usages with native ES eventually. |
| `jquery` | 1.11.10 | ⚠️ | Still pulled in by AutoForm + Summernote. Keep until those replacements (post-PWA) drop it transitively. |
| `http` | (latest) | ⚠️ | Deprecated in favour of `fetch`. Audit `server/` for any callers; this repo no longer uses it heavily — flag for removal. |
| `standard-minifier-css` | 1.8.1 | ✅ | |
| `standard-minifier-js` | 2.8.0 | ✅ | |
| `less` | (latest) | ✅ | |
| `service-configuration` | 1.3.0 | ✅ | Used by OAuth (GitHub / Google). |
| `accounts-ui` | 1.4.2 | ⚠️ | We render auth via custom Blaze templates (A9.32). Audit whether `accounts-ui` is still imported by any view; if not, drop. |
| `accounts-password` | 2.3.1 | ✅ | |
| `accounts-github` | 1.5.0 | ✅ | |
| `accounts-google` | 1.4.0 | ✅ | |
| `email` | 2.2.1 | ✅ | |
| `ddp-rate-limiter` | (latest) | ✅ | `server/rate-limits.js` keeps working. |
| `browser-policy-content` | (latest) | ✅ | |
| `browser-policy-framing` | (latest) | ✅ | |
| `meteortesting:mocha` | (latest) | ✅ | Has Meteor 3 build. |
| `spacebars` | 1.0.12 | ✅ | |
| `facebook-config-ui`, `github-config-ui`, `google-config-ui`, `meteor-developer-config-ui`, `twitter-config-ui` | various | 🗑️ | Only `github-config-ui` + `google-config-ui` are actually wired; the others can drop. Verify against `accounts.js`. |
| **iron:router** | latest | ❌ | **Biggest single risk.** Maintenance status is ambiguous for Meteor 3. Two paths: (a) pin to community fork (verify on prep branch); (b) migrate `router.js` to **FlowRouter** + `kadira:dochead` for `<head>` writes. Route count is ~12 — a migration is tractable in 2–3 days. Recommend path (b) for long-term health. |
| **zimme:iron-router-active** | latest | ❌ | Tied to iron:router. If we go FlowRouter, replace with `arillo:flow-router-helpers` (`isActiveRoute`) — trivial template-helper swap. |
| **ostrio:iron-router-title** | latest | ❌ | Same fate. `kadira:dochead` covers the same surface. |
| **meteorhacks:subs-manager** | latest | ❌ | Last release predates Meteor 3. Replace with a ~30-line custom `SubsManager`-equivalent in `both/lib/environment.js` (LRU cache of `Meteor.subscribe(...)` handles by computed key). Touches `router.js` + a handful of `Template.X.onCreated` blocks. |
| **percolatestudio:synced-cron** | latest | ❌ | Replace with `quave:synced-cron` (community Meteor 3 maintenance). Same API surface, no caller changes in `server/cron.js`. |
| **percolate:migrations** | latest | ⚠️ | Verify Meteor 3 build; if not, `quave:migrations` is the analogue. Touches `server/migrations.js` only. |
| **aldeed:autoform** | latest | ⚠️ | Has a Meteor 3 line. Async hooks (`hooks.before/after`) must be `async` — touches `client/views/jobs/jobForms.js` and `client/views/user/userAccount.js`. |
| **aldeed:collection2** | latest | ⚠️ | Same author. Verify the version compatible with the chosen `autoform` line; check schema attach in `both/collections/*.js`. |
| **dburles:collection-helpers** | latest | ✅ | Pure client/server JS, no Fibers. |
| **reywood:publish-composite** | latest | ⚠️ | Audit whether we still use it; if so verify the Meteor 3 build. |
| **natestrauser:publish-performant-counts** | latest | ⚠️ | Niche package; consider replacing with our own `Meteor.publish` cursor counts if no Meteor 3 build exists. Currently powers count helpers — limited blast radius. |
| **alanning:roles** | latest | ⚠️ | Has Meteor 3 builds; verify version pin. |
| **nemo64:bootstrap** | latest | 🗑️ | Pre-A9.32 Bootstrap 3 import; the BS5 migration replaced this with the npm `bootstrap` package. Confirm and drop. |
| **peppelg:bootstrap-3-modal** | latest | 🗑️ | BS3-only. BS5 has native modal. Drop after auditing for callers. |
| **mpowaga:autoform-summernote** | latest | ⚠️ | Drags jQuery + Summernote; verify Meteor 3 build. Touches the post-a-job form description editor. Consider replacing with a slimmer ContentEditable component during the Mobile UX phase. |
| **djedi:sanitize-html** | latest | ⚠️ | Verify Meteor 3 build; if no, swap for the npm `sanitize-html` package directly. |
| **gadicohen:sitemaps** | latest | ⚠️ | `server/sitemap.js` is the only caller. If unmaintained, our sitemap is small enough to rewrite as a route handler in ~40 lines. |
| **lampe:rssfeed** | latest | ⚠️ | `server/rss.js` is the only caller. Same fallback as sitemap if no Meteor 3 build exists. |
| **raix:handlebar-helpers** | latest | ⚠️ | Verify; if not we replace with the small set of helpers we actually use (~6) directly in `client/helpers.js`. |
| **momentjs:moment** | =2.15.1 | ❌ | Pinned to a 2026-stale version. Replace with npm `dayjs` (smaller, modern, async-safe). Touches every `{{relativeTime}}` / `moment(...).fromNow()` call — ~15 sites. Bundle win alone justifies it. |
| **utilities:avatar** | latest | ⚠️ | Verify build. |
| **natestrauser:connection-banner** | latest | ⚠️ | Cosmetic; if no Meteor 3 build, replace with our own 30-line Blaze template wired to `Meteor.status()`. |
| **aldeed:delete-button** | latest | ⚠️ | Verify. |
| **nimble:restivus** | latest | ⚠️ | Powers `/api/jobs` in `server/api.js`. If no Meteor 3 build, replace with a `WebApp.connectHandlers.use(...)` JSON handler — ~40 lines. |
| **natestrauser:uploadcare-plus** | latest | ⚠️ | Audit caller; consider replacing with direct Uploadcare JS widget (npm). |
| **ongoworks:speakingurl** | latest | ⚠️ | Powers `Jobs.helpers.slug()`. Tiny; replace with npm `speakingurl` directly if no Meteor 3 build. |
| **mdg:seo** | latest | ❌ | Unmaintained for years. Replace with the existing `client/lib/seo.js` already in this codebase — it just needs to set `<meta>` + `<title>` tags directly via DOM API + a small server-render fallback for crawlers. |
| `force-ssl@1.1.0` | — | 🗑️ | Already commented out. Remove the comment block as part of the prep PR. |
| `yogiben:admin`, `useraccounts:bootstrap`, `useraccounts:iron-routing`, `staringatlights:infinite-scroll`, `copleykj:stripe-sync`, `astronomerio:core`, `shwaydogg:space-monkey`, `multiply:iron-router-progress`, `pauli:accounts-linkedin`, `matb33:collection-hooks` | various | 🗑️ | All already commented out. Remove the comment blocks during the prep PR to shrink the file. |

## Fibers-removal surface (mechanical)

Every `Promise.await(...)` call on the server becomes `await ...`, and
the enclosing function gains `async`. Known sites:

- `server/methods.js` — `featuredJob.checkout` is already `async`; the
  remaining method bodies (jobs.*, users.*, jobs.count) need the same
  treatment.
- `server/publications.js` — `featuredJobs` $sample pipeline.
- `server/dev-accounts.js` — seed pipeline.
- `server/migrations.js` — migration runners.
- `server/cron.js` — synced-cron handlers.
- `server/stripe-webhook.js` — `setFeaturedFromSession`, `revokeFeatured`.
- `server/sitemap.js`, `server/rss.js`, `server/api.js` — collection
  reads that currently block on Fibers.
- `server/startup-checks.js`, `server/healthz.js` — Mongo pings.

A codemod (`scripts/remove-fibers.mjs`) lands as part of the prep PR
and is the single commit that does the mechanical sweep so the diff
is reviewable.

## Test coverage uplift (B28)

Today we have `tests/methods.tests.js` + `tests/helpers.tests.js` but
no coverage of publications. The upgrade gate adds:

- `tests/publications.tests.js` — assert each pub returns the expected
  doc shape + count for a seeded fixture.
- `tests/router.tests.js` — assert each route resolves and renders the
  expected template (catches regressions when we swap iron:router).
- `tests/payments.tests.js` — assert the new payment-provider
  abstraction (Phase 4) routes simulator calls correctly.

These run on the current branch first to lock current behaviour, then
serve as the regression net for the upgrade branch.

## Node / runtime

- Bump `Dockerfile.dev` and `Dockerfile.prod` from Node 18 → 20.
- Update `package.json#engines.node` to `>=20.0.0 <21.0.0`.
- CI workflow (`.github/workflows/ci.yml`) actions/setup-node to `node-version: 20`.

## Settings

No settings schema changes are required for the Meteor upgrade itself.
The new mobile-money + PWA features ship their own settings keys
(see `settings-example.json`).

## Order of operations on `upgrade/meteor-3`

1. Run the prep PR on `main`: drop 🗑️ packages, add the test
   coverage uplift (B28). Lands without functional change.
2. Branch `upgrade/meteor-3` off the post-prep `main`.
3. Replace each ❌ in the table above, one PR per swap, merged back
   into the upgrade branch. Each PR keeps full test green.
4. Codemod for Fibers removal (`scripts/remove-fibers.mjs`) lands as
   a single mechanical commit.
5. `meteor update --release 3.x` + Node bump.
6. Burn-in week on staging UAT stack; full Playwright sweep.
7. Production cutover during a low-traffic window with a rollback
   plan to a tagged Meteor 2.7.1 image.

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| iron:router has no viable Meteor 3 path | M | High | FlowRouter spike done **before** committing to the upgrade. |
| AutoForm / Summernote stack incompatible | L | Medium | Replace with custom Blaze form during Mobile UX phase if needed. |
| Mongo driver behaviour shift on aggregation | L | Medium | Publication tests (B28) catch this. |
| Cordova hot-code-push semantics change | M | Medium | We are dropping Cordova in favour of Capacitor (Phase 5); no live Cordova clients. |
| Hidden Fibers in atmosphere packages we don't own | M | Medium | Codemod is mechanical; runtime errors surface immediately in tests. |

