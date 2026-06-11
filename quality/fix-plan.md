# Screenshot Analysis Fix Plan

> **Point-in-time artifact** from quality run `2026-05-25_092945`. Superseded
> by the 2026-06-10 run (`.quality-run/results/2026-06-10_120309/` —
> `fix-plan/execution-plan.json` and `docs/product/BACKLOG.md` are the
> current trackers). Item statuses below are NOT maintained.

## Executive Summary

- **Source inputs:** `.quality-run/results/2026-05-25_092945/screenshot-analysis/fix-plan.json` and `summary.md`
- **Total findings:** 76
- **Severity breakdown:** 44 critical, 20 high, 10 medium, 2 low
- **Category breakdown:** 38 rendering, 38 ux-regression
- **Affected personas:** **Carlos (employer)** worst, **Ana (seeker)** second, **Marta (admin)** third, **Visitor** clean
- **Deduped outcome:** the 76 findings collapse into **3 primary fix items** plus **2 deferred investigations/design calls**

The screenshot set is dominated by one repeated root cause: a duplicated sticky navigation bar appearing mid-page in full-page screenshots. Once that is addressed, the remaining product issues are concentrated in the employer job-post flow (unexpected `Internal server error`) and the underdesigned `/myjobs` empty state.

---

## Priority Order

1. **FIX-001** — Stabilize sticky header behavior during headed screenshot capture and long-page rendering
2. **FIX-002** — Make job creation resilient and restore the expected success state after posting
3. **FIX-003** — Add a real in-body empty state to `/myjobs`
4. **Deferred investigations/design calls** — only after the three items above are re-run through headed E2E + screenshot analysis

---

## Deduplicated & Grouped Issues

### FIX-001: Remove duplicated sticky header from confirmation and long-form screenshots
**Severity:** critical | **Category:** rendering | **Effort:** medium  
**Affects:** Ana (seeker), Carlos (employer), Marta (admin) | **Browsers:** both (Firefox worst)  
**Screenshots:** `firefox-journey-seeker-step-1-register.png`, `firefox-journey-seeker-step-2-verified.png`, `firefox-journey-employer-step-1-register.png`, `firefox-journey-admin-step-1-register-admin.png`, `chromium-journey-employer-step-3-validation.png`, `firefox-journey-employer-step-3-validation.png`, `chromium-journey-employer-step-4-job-created.png`, `firefox-journey-employer-step-4-job-created.png`, `chromium-journey-employer-step-5-job-email.png`, `firefox-journey-employer-step-5-job-email.png`

**Problem:**  
A duplicated navigation/header strip is rendered across the middle of the page, cutting through the sign-up confirmation card and the employer job form. This drives most of the critical rendering, layout-containment, CTA-visibility, text-legibility, and modal-stacking failures. The visual evidence is consistent with the same sticky header being captured more than once during long/full-page screenshots.

**Root Cause:**  
Best current hypothesis is **sticky header + full-page screenshot stitching**, not ten separate UI bugs:
- `frontend/src/components/layout/Header.tsx` uses `sticky top-0`
- all journey specs call `page.screenshot({ fullPage: true })`
- only taller pages/screens get the duplicated header artifact; visitor flows remain clean because they are shorter
- Firefox shows it even on shorter auth confirmation pages, so the issue is browser-sensitive but still the same root cause family

**Suggested Fix:**
- Centralize screenshot capture into a shared helper and stop using raw `fullPage: true` on pages with sticky chrome
- Either:
  - switch visual audit screenshots to viewport-only capture for journey evidence, **or**
  - temporarily disable sticky positioning before capture (for example by toggling a test-only attribute/class on the app shell)
- If product screenshots must remain full-page, add a layout-level opt-out so auth confirmation and form-heavy routes can render the header as non-sticky during capture mode
- Re-run headed E2E on Chromium + Firefox before accepting any remaining rendering findings as product defects

**Files to Change:**
- `tests/e2e/journey-seeker.spec.js` — replace per-spec `snap()` logic with a shared safe screenshot helper
- `tests/e2e/journey-employer.spec.js` — same as above; this file contributes the longest failing pages
- `tests/e2e/journey-admin.spec.js` — same as above
- `tests/e2e/journey-visitor.spec.js` — keep screenshot behavior consistent across suites
- `tests/e2e/journey-multiuser.spec.js` — keep screenshot behavior consistent across suites
- `frontend/src/components/layout/Header.tsx` — optionally support a capture mode / non-sticky variant
- `frontend/src/app/layout.tsx` — pass route- or test-aware layout flags if needed
- `frontend/src/app/globals.css` — if the final fix uses a CSS override for screenshot mode

**Verification:**  
Re-run headed journeys for seeker, employer, and admin in Chromium + Firefox. The header should appear once at the top only; no mid-page overlay should remain in the listed screenshots.

---

### FIX-002: Restore successful employer job posting instead of showing `Internal server error`
**Severity:** critical | **Category:** ux-regression | **Effort:** medium  
**Affects:** Carlos (employer) | **Browsers:** both  
**Screenshots:** `chromium-journey-employer-step-4-job-created.png`, `firefox-journey-employer-step-4-job-created.png`, `chromium-journey-employer-step-5-job-email.png`, `firefox-journey-employer-step-5-job-email.png`

**Problem:**  
After the employer submits the job form, the expected success state never appears. Instead, the user remains on the form and sees a maroon `Internal server error` banner. The manifest expected a created-job state with the new job title visible, and the follow-up “job received” email step is therefore also visually wrong.

**Root Cause:**  
Most likely the `/jobs` creation flow succeeds only partially and then fails on a secondary operation. The strongest candidate is the synchronous submission email side-effect in `backend/app/routers/jobs.py`:
- job is saved first
- then `send_job_submitted_email(...)` is called inline
- any SMTP/runtime exception would surface as a 500 and the frontend would show the generic banner

There is also a frontend resilience gap: `frontend/src/components/jobs/JobForm.tsx` treats the entire submit as failed instead of distinguishing “job saved, notification failed” from “job was not created”.

**Suggested Fix:**
- Wrap post-create email dispatch so it **cannot** turn a successful job creation into a 500
- Move submission email sending to a safer path (background task, best-effort notification, or guarded `try/except` with logging)
- Return the created job response even if email delivery fails
- Improve the frontend submit handler to redirect to the created job page when the API returns success, and reserve the red banner for true create failures only
- Add automated coverage for “SMTP unavailable but job creation still succeeds”

**Files to Change:**
- `backend/app/routers/jobs.py` — decouple `send_job_submitted_email(...)` from the critical request path
- `backend/app/services/email.py` — ensure email send failures are surfaced as controlled failures/logs, not request-killing surprises
- `backend/app/main.py` — keep logging rich enough to diagnose the exact create-job traceback in development/UAT
- `frontend/src/components/jobs/JobForm.tsx` — preserve success redirect/state handling and make notification failure non-blocking
- `backend/tests/test_jobs.py` — add regression coverage for successful create when notifications fail
- `tests/e2e/journey-employer.spec.js` — keep the current fallback, but once fixed this journey should pass without DB insertion fallback

**Verification:**  
Post a job through the UI with SMTP/MailHog available **and** with email delivery intentionally unavailable. In both cases, job creation should return success, redirect away from `/jobs/new`, and show the created job or pending-review state.

---

### FIX-003: Add an actionable empty state to `/myjobs`
**Severity:** critical | **Category:** ux-regression | **Effort:** small  
**Affects:** Ana (seeker) primarily; also any signed-in user with zero jobs | **Browsers:** chromium/firefox  
**Screenshots:** `chromium-journey-seeker-step-5-myjobs.png`, `firefox-journey-seeker-step-5-myjobs.png`

**Problem:**  
The empty `/myjobs` page shows only the sentence `You have not posted any jobs yet.` in a large empty area. There is no clear in-body primary action, so the page feels unfinished and the expected next step is unclear. The only visible “Post a job” action is the global header link, which is too weak and too indirect for an empty-state recovery flow.

**Root Cause:**  
`frontend/src/app/myjobs/page.tsx` renders a plain text fallback when `jobs.length === 0` and does not provide:
- an inline CTA
- supporting explanatory copy
- a container/card that visually anchors the empty state

**Suggested Fix:**
- Replace the plain text fallback with a proper empty-state card
- Add a prominent in-body primary CTA (`Post a job`) linking to `/jobs/new`
- Add secondary explanatory copy so the state feels intentional rather than broken
- Optionally add a lightweight icon/illustration and a secondary action if product wants a softer path (for example, “Browse jobs” or “Return home”)

**Files to Change:**
- `frontend/src/app/myjobs/page.tsx` — replace the bare paragraph with a structured empty-state block
- `frontend/src/components/ui/Button.tsx` — only if a button variant/layout tweak is needed for the new CTA
- `frontend/src/components/layout/Container.tsx` — only if a reusable empty-state wrapper is introduced

**Verification:**  
Visit `/myjobs` as a signed-in user with no jobs. The page body should contain a visible, primary in-context CTA and supporting copy; the screenshot should no longer fail for missing CTA / incomplete journey intent.

---

## Dependency Map

- **FIX-001 first**
  - Most of the screenshot failures are downstream of the duplicated sticky header artifact
  - Do this before spending time on pixel-level layout tweaks for auth or form pages
- **FIX-002 second**
  - Once screenshots are trustworthy, fix the real employer submission failure
  - This unblocks the expected success state and makes the email check step meaningful again
- **FIX-003 third**
  - Independent product improvement with low implementation risk
  - Can be done in parallel if needed, but it does not unblock the screenshot-noise problem

**Graph:**
- `FIX-001 -> re-run screenshot analysis -> validate remaining rendering issues`
- `FIX-002 -> re-run employer journey -> confirm step-4 and step-5 success states`
- `FIX-003 -> re-run /myjobs empty-state screenshots`

---

## Quick Wins (<=30 min, high leverage)

1. **Replace `fullPage: true` in screenshot capture or centralize a safe helper**  
   Likely resolves the bulk of duplicated-header findings across seeker, employer, and admin flows.

2. **Add an in-body CTA card to `/myjobs`**  
   One small page-level change resolves both browser variants of the empty-state failures.

3. **Guard `send_job_submitted_email(...)` with `try/except` + logging**  
   If email dispatch is the 500 trigger, this should immediately restore the expected success path for employer posting.

---

## Deferred Items

### Deferred 1: Decide whether auth confirmation pages should keep global sticky chrome
The immediate evidence points to screenshot capture behavior, not a product-only layout bug. Before changing the production auth experience, confirm whether the intended fix is:
- test-only screenshot handling, or
- a real UX change that removes/softens the sticky header on `/sign-up` success and `/verify-email/[token]`

**Files likely involved if promoted from deferred to active:**
- `frontend/src/app/sign-up/page.tsx`
- `frontend/src/app/verify-email/[token]/page.tsx`
- `frontend/src/components/layout/Header.tsx`

### Deferred 2: Confirm the intended role behavior for `/myjobs`
The failing screenshots were captured in the seeker journey, but the current page language and expected CTA are employer-oriented (`Post a job`). Product/design should confirm whether `/myjobs` is meant to:
- stay as a shared dashboard for all signed-in users,
- become role-aware, or
- redirect seekers to a different page entirely

**Files likely involved if promoted from deferred to active:**
- `frontend/src/app/myjobs/page.tsx`
- `frontend/src/contexts/AuthContext.tsx`
- `frontend/src/hooks/useAuth.ts`

---

## Recommended Execution Sequence

1. Implement **FIX-001** and re-run headed screenshots in Chromium + Firefox
2. Implement **FIX-002** and re-run the employer journey end-to-end
3. Implement **FIX-003** and re-run the `/myjobs` screenshot path
4. Re-open deferred items only if failures remain after the first re-run

This sequence should remove the screenshot noise first, then fix the genuine employer-blocking defect, then clean up the remaining empty-state UX gap.
