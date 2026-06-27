---
last_verified: 2026-06-27T00:00:00Z
git_ref: master
verified_by: codebase-cartographer — FP-CARTO-007 doc refresh (2026-06-14)
---

# Route Map — Employed frontend (Next.js App Router)

Routes observed under `frontend/src/app/`. Gating is enforced by
`frontend/middleware.ts` via cookies (`employed_token` presence,
`employed_is_admin === "1"`); this is UX-level only — real authorization
lives in the API (`require_admin`, ownership checks).

Every page renders inside `src/app/layout.tsx`: market resolved from request
headers (`resolveMarketFromHeaders`), `<html lang>` set to the market locale,
`RuntimeEnvScript` injects `window.__ENV` per request (EMP-012), providers:
`NextIntlClientProvider` → `MarketProvider` → `AuthProvider`.

## Pages

| Route | File | Gate | Purpose / key components |
|-------|------|------|--------------------------|
| `/` | `page.tsx` | public | Market home: hero, `FeaturedStrip`, `JobGrid` |
| `/jobs` | `jobs/page.tsx` | public | Listing with `JobFilters`, `Pagination`; data from API `/api/jobs` |
| `/jobs/[id]` | `jobs/[id]/page.tsx` | public | Job detail (`JobDetail`); non-active listings 404 unless owner/admin (API-enforced) |
| `/jobs/new` | `jobs/new/page.tsx` | public | Post a job (`JobForm`, `RecaptchaWidget` for anonymous, `RichTextEditor`) |
| `/jobs/[id]/edit` | `jobs/[id]/edit/page.tsx` | auth | Edit own job (`JobForm`) |
| `/myjobs` | `myjobs/page.tsx` | auth | Owner dashboard: `MyJobCard`, `FeatureJobModal`, `PaymentPoller` |
| `/account` | `account/page.tsx` | auth | `AccountSettings`, `ExportDataButton`, `DeletionSection`, resend verification |
| `/admin/jobs` | `admin/jobs/page.tsx` | admin | Moderation: `StatusTabs`, `AdminJobTable`, `BulkActionBar`, `AdminUsersList` (search + promote, EMP-015), `ReportsPanel`. Panels degrade independently on fetch failure (EMP-026b) |
| `/sign-in` | `sign-in/page.tsx` | public | `LoginForm`, `OAuthButtons` (Google only); honors `?redirect=` |
| `/sign-up` | `sign-up/page.tsx` | public | `RegisterForm` |
| `/forgot-password` | `forgot-password/page.tsx` | public | `ForgotPasswordForm` |
| `/reset-password/[token]` | `reset-password/[token]/page.tsx` | public (token) | `ResetPasswordForm` — target of password-reset email links (EMP-004) |
| `/verify-email/[token]` | `verify-email/[token]/page.tsx` | public (token) | `VerifyEmail` — target of verification email links (EMP-004) |
| `/privacy`, `/terms` | `privacy/page.tsx`, `terms/page.tsx` | public | Legal |
| not found | `not-found.tsx` | public | 404 |

## Route handlers / metadata routes

| Route | File | Notes |
|-------|------|-------|
| `/api/health` | `api/health/route.ts` | Static health JSON; Docker healthcheck target |
| `/robots.txt` | `robots.ts` | Sitemap URL derived from `NEXT_PUBLIC_APP_URL` (EMP-024) |
| `/sitemap.xml` | `sitemap.ts` | Static paths (`/`, `/jobs`, `/sign-in`, `/sign-up`) × both market hosts, derived from `NEXT_PUBLIC_APP_URL` |

## Middleware behavior (`frontend/middleware.ts`)

- Matcher: `/myjobs`, `/account`, `/admin/:path*`, `/jobs/:path*/edit`, and
  all non-asset paths.
- No `employed_token` cookie on a gated route → redirect to
  `/sign-in?redirect=<original>`.
- `/admin/*` without `employed_is_admin=1` → redirect to `/`.
- Sets `x-next-intl-locale` response header from hostname (`mx.*` → `es`,
  else `pt`) for server-side next-intl resolution
  (complements `src/i18n/request.ts`).

## Localization

- Catalogs: `frontend/messages/{en,pt,es}.json` — 263 keys each, kept in
  sync (gate from the 2026-06-10 run). pt/es coverage completed across auth,
  job-detail, account, my-jobs and post-job surfaces (EMP-027).
- Locale never appears in the URL path; it is purely hostname-derived.
  Locale codes en/pt/es only.

## Session/auth client flow (`src/contexts/AuthContext.tsx`)

- Login/refresh use `credentials: "include"` so the httpOnly
  `employed_refresh_token` cookie (path=/auth) flows; refresh token is held
  in memory per tab, never localStorage (EMP-006).
- Access token: localStorage `employed_token` + same-named non-httpOnly
  cookie for the middleware; proactive refresh scheduled ~60 s before JWT
  expiry; cross-tab sync via storage events.
- Logout posts to `/auth/logout` (revokes JTI) and clears token/admin
  cookies.
- All API calls send `X-Forwarded-Host` with the current browser/server host
  so the backend resolves the same market (EMP-001 contract).
