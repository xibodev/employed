# Employed — UI/UX Redesign Plan

> **Status (May 2026):** This document is a **point-in-time audit and
> design plan** captured from the legacy pre-migration UI. The repository
> now runs on FastAPI + Next.js, so treat this file as **historical
> context**, not a current implementation spec.

> Audit conducted May 2026 against the live Docker dev environment.  
> Screenshots captured at 1440×900 (desktop) and 390×844 (iPhone 14 proxy).

---

## 1. Executive Summary

Employed is a focused, no-nonsense job board for emerging markets (Mozambique, Mexico). The product idea is strong — local, free, multilingual. The legacy UI audited here was a lightly-customised Bootstrap 3 theme from ~2015. It worked, but it communicated "side project" rather than "trusted local institution." The redesign goal was not to add features — it was to make every existing interaction feel intentional, fast, and trustworthy, especially on mobile where most of the target audience lives.

**Three core problems to solve:**
1. The visual language is generic and dated — zero brand identity
2. The job browsing experience is passive — no hierarchy, no scannability
3. The job posting flow is intimidating — a wall of form fields with a rich-text editor that breaks on mobile

---

## 2. Current State Audit

### 2.1 Design Tokens (measured)

| Token | Current value | Problem |
|---|---|---|
| Primary font | Montserrat | Good choice, but weight/size usage is inconsistent |
| Body text color | `#666666` | Fails WCAG AA on white (contrast 5.7:1 — borderline) |
| Primary action color | `#b73737` (dark red) | Arbitrary, no brand story, clashes with Bootstrap defaults |
| Border radius | `0px` everywhere | Feels hard and dated |
| Card border | `1px solid #ddd` | Invisible on white, no depth |
| Jumbotron bg | `#27272b` (near-black) | Good dark anchor, but underused |
| Footer bg | `#27272b` | Consistent with jumbotron — keep |
| Button radius | `0px` | Sharp corners feel aggressive |

### 2.2 Page-by-Page Issues

#### Home (`/`)
- **Hero is too tall on desktop, too short on mobile.** The jumbotron has no `min-height`, so on mobile it collapses to ~180px — barely enough to read the tagline before the CTA buttons.
- **Two CTAs compete equally.** "Browse Jobs" and "Post a Job" are the same size, same weight. For a job seeker (the majority), "Browse Jobs" should be primary. For an employer, "Post a Job" is secondary. They need visual hierarchy.
- **"Recent Jobs" section is empty-state-blind.** When there are no jobs, the section just shows a heading and a "See all jobs" link. No illustration, no copy explaining why it's empty, no encouragement.
- **No value proposition below the fold.** After the hero, there's nothing that explains *why* this platform exists, what makes it different, or who it's for. A first-time visitor has no reason to trust it.
- **The RSS link in the recent jobs header is invisible.** A small icon next to a heading — no one finds it.

#### Jobs Listing (`/jobs`)
- **Job cards are text-only rows with no visual weight.** Company name, location, job type, and date are all the same size and color. The eye has nowhere to land.
- **No company logo / avatar placeholder.** Every modern job board uses a company initial or logo. The absence makes listings feel anonymous.
- **Filter bar is functional but ugly.** Three controls (search, type dropdown, remote checkbox) are stacked vertically with no visual grouping. On mobile they take up 40% of the viewport before any jobs appear.
- **No empty state illustration.** When search returns nothing, a plain `<h4>` says "No active jobs found." — no guidance, no suggestion to clear filters.
- **Pagination / load-more is hidden.** The "Load more" button only appears when there are >50 jobs. With 2 jobs in the demo it's invisible, but the UX pattern (a button at the bottom) is weak — infinite scroll or numbered pages would be better.
- **No job count.** Users don't know if they're looking at 2 jobs or 200.

#### Job Detail (`/jobs/:id/:slug`)
- **The layout is a single column with no sidebar.** On a 1440px screen, a paragraph of job description stretches to ~900px wide — unreadable. The 3-column grid (`col-sm-3` / `col-sm-9`) is the right idea but the left column (metadata) is too narrow and the right column (description) is too wide.
- **The "Apply" action is missing.** There is no prominent CTA to apply. The contact email is buried in the metadata column in the same weight as the date. A job seeker has to hunt for how to apply.
- **Featured upgrade upsell is shown to the job owner inline in the description.** This is confusing — a visitor sees "Buy 30 days for MZN 2,500" before they read the job description.
- **Status alerts (pending, filled) use Bootstrap's default blue/grey.** They don't feel like part of the brand.
- **The admin status toggle is shown inline on the public job page.** Mixing moderation controls with the public view creates cognitive noise for admins and is confusing if a non-admin ever sees it (they don't, but the layout implies it).

#### Post a Job (`/job`)
- **The Summernote rich-text editor is completely broken on mobile.** The toolbar overflows the viewport. Users on phones cannot format text.
- **The form is one long scroll with no progress indication.** 8 fields + a rich text editor + a submit button. No sections, no grouping, no sense of "you're almost done."
- **The policy text ("This site is protected by reCAPTCHA...") appears mid-form** between the description and the URL field. It should be at the bottom near the submit button.
- **The submit button label is "Continue to preview your post"** — but there is no preview step. The button submits directly. This is a broken promise.
- **No character count on the description field.** The schema allows 50,000 chars. Users have no feedback.

#### Sign In / Sign Up (`/sign-in`, `/sign-up`)
- **The OAuth buttons say "Configure Github" / "Configure Google"** — these are admin setup labels, not user-facing labels. A visitor sees "Configure Github" and thinks it's a settings page, not a login option.
- **The form is centered in a narrow column with no surrounding context.** No brand mark, no tagline, no reason to trust the page. It looked like a generic legacy accounts template.
- **No "remember me" option.**
- **Password field has no show/hide toggle.**

#### My Jobs (`/myjobs`)
- **The page is a plain list with no actions.** Each job shows title, type, date, company, location — but no status badge, no quick-edit link, no delete button. The user has to click into each job to manage it.
- **No empty state.** If a user has no jobs, the page is blank below the heading.

#### Admin (`/admin/jobs`)
- **The status tabs are plain Bootstrap nav-tabs** with no count badges except on "Pending." All tabs should show counts.
- **The bulk action bar is always visible** even when nothing is selected. The disabled "Apply" button creates visual noise.
- **The admin users panel and the reports panel are on the same page as job moderation**, separated only by `<hr>`. These are three distinct concerns that deserve their own sections or sub-routes.
- **The report reason is shown as a raw enum value** ("spam", "wrong_country") — not a human-readable label.

#### Account (`/account`)
- **The "Delete account" section uses the same visual weight as "Export data."** Destructive actions need visual separation and a danger color.
- **The page has no navigation back to other sections.** It's a dead end.

---

## 3. Redesign Principles

These are the constraints that should govern every decision:

1. **Mobile-first, always.** The target markets (Mozambique, Mexico) have high mobile usage. Every layout decision starts at 390px and expands up.
2. **Speed over decoration.** No heavy animations, no image carousels, no JavaScript-heavy widgets. Keep the client bundle lean.
3. **Trust through clarity.** Emerging market users are skeptical of new platforms. Clear copy, visible contact info, and consistent visual language build trust faster than polish.
4. **Build against the current stack.** This audit was captured against the legacy Blaze/Bootstrap implementation, but any remaining redesign work should be applied in the current FastAPI + Next.js codebase rather than by reviving Meteor-era patterns.
5. **Accessibility baseline.** WCAG AA contrast on all text. Keyboard navigable. Semantic HTML (already mostly there).

---

## 4. Design System Changes

### 4.1 Color Palette

Replace the arbitrary dark-red with a purposeful palette rooted in the brand's geographic identity.

```
-- Primary (action, links, focus)
  Indigo-600:  #4F46E5   (replaces #b73737)
  Indigo-700:  #4338CA   (hover state)
  Indigo-100:  #E0E7FF   (light tint for badges, backgrounds)

-- Neutral (text, borders, surfaces)
  Gray-900:    #111827   (headings)
  Gray-700:    #374151   (body text — replaces #666, passes WCAG AA)
  Gray-500:    #6B7280   (secondary text, metadata)
  Gray-200:    #E5E7EB   (borders, dividers)
  Gray-50:     #F9FAFB   (page background, card backgrounds)

-- Semantic
  Green-600:   #16A34A   (active/success states)
  Amber-500:   #F59E0B   (pending/warning states)
  Red-600:     #DC2626   (danger, destructive actions)
  Blue-600:    #2563EB   (informational)

-- Brand dark (keep existing jumbotron/footer)
  Dark:        #27272B   (hero, footer — unchanged)
```

**Why indigo?** It reads as professional and digital without the aggression of red or the blandness of blue. It's uncommon in African/Latin American job boards, giving Employed a distinctive identity.

### 4.2 Typography Scale

Keep Montserrat. Fix the usage:

```
Display (hero h1):    48px / 700 / -0.02em  (down from 68px — too large)
H1 (page title):      32px / 700 / -0.01em
H2 (section title):   24px / 600
H3 (card title):      18px / 600
Body:                 16px / 400 / 1.6 line-height
Small / meta:         14px / 400
Label:                12px / 600 / uppercase / 0.05em tracking
```

### 4.3 Spacing & Radius

```
Border radius:
  sm:   4px   (inputs, badges)
  md:   8px   (cards, buttons)
  lg:   12px  (modals, panels)
  full: 9999px (pills, tags)

Spacing scale: 4px base (4, 8, 12, 16, 24, 32, 48, 64, 96)
```

### 4.4 Shadows

Replace Bootstrap's flat borders with subtle elevation:

```
card:    0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04)
hover:   0 4px 12px rgba(0,0,0,0.10), 0 2px 4px rgba(0,0,0,0.06)
modal:   0 20px 60px rgba(0,0,0,0.20)
```

---

## 5. Component Redesigns

### 5.1 Navigation

**Current:** White navbar, brand name left, links right, user dropdown. No visual separation from page content.

**Redesign:**
- Add a 1px `border-bottom: 1px solid #E5E7EB` to separate nav from content
- Brand name gets a small logomark (a simple geometric "E" or map-pin icon) — SVG, inline, 20px
- On mobile: hamburger collapses to a bottom sheet (not a dropdown) — easier thumb reach
- "Post a Job" in the nav becomes a filled indigo button, not a plain link — it's the primary revenue action
- User avatar uses initials in an indigo circle (already implemented) — keep, just restyle
- Language switcher moves to a globe icon with a tooltip — saves horizontal space

### 5.2 Hero / Jumbotron

**Current:** Dark background, centered text, two equal CTA buttons, no imagery.

**Redesign:**
```
┌─────────────────────────────────────────────────────────────┐
│  [dark bg #27272B]                                          │
│                                                             │
│  Employed MZ                          [subtle map pattern   │
│  Local jobs. Local hiring.             or abstract geo      │
│                                        illustration, right  │
│  Explore active vacancies or post      side, 40% opacity]  │
│  an opportunity for local candidates.                       │
│                                                             │
│  [Browse Jobs →]  [Post a Job]                              │
│                                                             │
│  ── 2 active jobs ── Free to post ── 90-day listings ──    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```
- Min-height: 420px desktop, 320px mobile
- "Browse Jobs" = filled indigo button (primary)
- "Post a Job" = ghost button with white border (secondary)
- Add a trust bar below the CTAs: job count, "Free to post", "90-day listings" — three short facts separated by dots
- On mobile: stack buttons full-width, trust bar wraps to 2 lines

### 5.3 Job Card (listing)

**Current:** Plain text row — title, type badge, date, company, location. No visual hierarchy.

**Redesign:**
```
┌──────────────────────────────────────────────────────────┐
│  [EH]  Senior Frontend Developer          Contract  🌐   │
│        Employed HQ · Maputo               2 days ago     │
└──────────────────────────────────────────────────────────┘
```
- Company initial avatar (40×40, rounded, indigo bg) — left-anchored
- Job title: 16px/600, Gray-900 — the dominant element
- Type badge: pill shape, indigo-100 bg, indigo-700 text
- Remote badge: globe emoji or icon, only shown when remote=true
- Company · Location: 14px, Gray-500, on one line
- Date: 14px, Gray-400, right-aligned
- Hover: card lifts with shadow, title underlines
- Featured jobs: left border `4px solid #F59E0B` (amber), subtle amber-50 background

### 5.4 Job Detail Page

**Current:** Single column, metadata left (col-sm-3), description right (col-sm-9), no apply CTA.

**Redesign (desktop):**
```
┌─────────────────────────────────────────────────────────────┐
│  HEADER BAND (indigo-50 bg)                                 │
│  [EH]  Product Manager                                      │
│        Employed HQ · Maputo, Mozambique · Full Time         │
│        Posted 21 May 2026                                   │
│                                                             │
│  [Apply / Contact →]                                        │
└─────────────────────────────────────────────────────────────┘
│                                    │                        │
│  DESCRIPTION (col-8)               │  SIDEBAR (col-4)       │
│                                    │                        │
│  [rich text content]               │  Job Details           │
│                                    │  ─────────────         │
│                                    │  Type: Full Time       │
│                                    │  Location: Maputo      │
│                                    │  Remote: No            │
│                                    │  Contact: jobs@...     │
│                                    │                        │
│                                    │  [Apply / Contact →]   │
│                                    │                        │
│                                    │  ─────────────         │
│                                    │  [Report this job]     │
└────────────────────────────────────┴────────────────────────┘
```
- Header band: indigo-50 background, company avatar large (64px), title as H1
- Apply button: large, full-width in sidebar, indigo — the #1 action
- Description column: max-width 680px, 18px body text, 1.7 line-height
- Sidebar: sticky on scroll (position: sticky, top: 80px)
- On mobile: header band → description → sidebar (stacked), apply button fixed at bottom of viewport

### 5.5 Post a Job Form

**Current:** One long form, broken rich-text editor on mobile, misleading submit label.

**Redesign — 3-step wizard:**

```
Step 1: The Basics          Step 2: The Details         Step 3: Review & Post
─────────────────────       ─────────────────────       ─────────────────────
Job Title *                 Description *               [Preview card]
Job Type *                  (plain textarea on           
Company                     mobile, Summernote           [Confirm & Post]
Location                    on desktop)                  
Remote? [toggle]            Application URL             
                            Contact *                   
[Next →]                    [Next →]                    
```

- Progress bar at top: 3 steps, filled indigo
- Step 1 is the minimum viable post — title, type, company, location, remote
- Step 2 is the content — description (plain `<textarea>` on mobile, Summernote on desktop via `SUMMERNOTE_OPTIONS_FOR_VIEWPORT`), URL, contact
- Step 3 is a live preview of the job card + the actual submit button labeled "Post Job"
- Each step fits on one mobile screen without scrolling
- Character counter on description field
- reCAPTCHA notice moves to Step 3, near the submit button

### 5.6 Sign In / Sign Up

**Current:** Centered form, OAuth buttons labeled "Configure Github/Google", no brand context.

**Redesign:**
```
┌──────────────────────────────────────────────────────────┐
│  [Left half — brand panel]    [Right half — form]        │
│                                                          │
│  Employed MZ                  Sign in to your account   │
│  Local jobs. Local hiring.                               │
│                               [email input]              │
│  "Find your next opportunity  [password input]  [show]   │
│   or hire local talent."      [Sign In]                  │
│                                                          │
│  ── Free ── Local ── Fast ──  ─── or ───                 │
│                               [GitHub]  [Google]         │
│                                                          │
│                               Don't have an account?    │
│                               [Create account]           │
└──────────────────────────────────────────────────────────┘
```
- Two-column layout on desktop (brand left, form right)
- Single column on mobile (form only, brand panel hidden)
- OAuth buttons labeled "Continue with GitHub" / "Continue with Google"
- Password field has show/hide toggle
- "Sign in" / "Create account" tabs at the top of the form panel

### 5.7 My Jobs Dashboard

**Current:** Plain list, no status, no actions.

**Redesign:**
```
My Jobs                                    [+ Post a New Job]
─────────────────────────────────────────────────────────────
[Status filter tabs: All | Active | Pending | Filled | Inactive]

┌──────────────────────────────────────────────────────────┐
│  Product Manager                    ● Active             │
│  Employed HQ · Maputo · Full Time                        │
│  Posted 21 May 2026                                      │
│  [Edit]  [Deactivate]  [Delete]                          │
└──────────────────────────────────────────────────────────┘
```
- Status badge: colored dot + label (green=active, amber=pending, gray=inactive, blue=filled)
- Inline action buttons per card: Edit, Deactivate, Delete — no need to navigate into the job
- Status filter tabs at the top
- Empty state: illustration + "You haven't posted any jobs yet" + "Post your first job →" CTA

### 5.8 Admin Panel

**Current:** All concerns on one page — moderation, admin users, reports.

**Redesign — tabbed sub-navigation:**
```
Job Moderation
─────────────────────────────────────────────────────────────
[Jobs (1 pending)] [Reports (0)] [Admins]
─────────────────────────────────────────────────────────────
```
- Three tabs: Jobs, Reports, Admins — each a distinct concern
- Jobs tab: status tabs with counts on ALL tabs (not just pending)
- Reports tab: reason shown as human-readable label ("Spam", "Wrong country", "Duplicate")
- Bulk action bar: hidden until at least one checkbox is checked (use CSS `visibility: hidden` → `visible`)
- Each job row: compact — title, company, country, date, status badge, action buttons inline
- Admins tab: clean table, grant form at bottom

---

## 6. Information Architecture Changes

### 6.1 Navigation Structure

**Current:**
```
[Employed MZ]  [All Jobs]  [Post a Job*]  [Language]  [Sign In] [Sign Up]
                                          (* only when signed in)
```

**Proposed:**
```
[Employed MZ]  [Jobs]  [Language 🌐]  [Sign In]  [Post a Job →]
                                                   (always visible, button style)
```
- "Post a Job" is always visible — it's the revenue action and should be discoverable by anonymous users
- When signed in, the user menu expands to: My Jobs / Account / Admin (if admin) / Sign Out
- Language switcher is an icon-only button to save space

### 6.2 URL Structure (no changes needed)

The current URL structure is clean:
- `/` — home
- `/jobs` — listing
- `/jobs/:id/:slug` — detail
- `/job` — post new (consider `/jobs/new` for consistency)
- `/jobs/:id/:slug/edit` — edit
- `/myjobs` — dashboard (consider `/dashboard` or `/my-jobs`)
- `/admin/jobs` — admin (consider `/admin` with sub-routes)

Minor suggestion: `/job` → `/jobs/new` is more RESTful and discoverable.

---

## 7. Mobile-Specific Fixes (Critical)

These are bugs, not enhancements:

| Issue | Fix |
|---|---|
| Summernote toolbar overflows on mobile | Replace with plain `<textarea>` on viewports < 768px (already have `SUMMERNOTE_OPTIONS_FOR_VIEWPORT` — just need to use a textarea fallback, not the mobile toolbar) |
| Hero collapses to ~180px on mobile | Add `min-height: 320px` to `.jumbotron` |
| Filter bar takes 40% of mobile viewport | Collapse filters behind a "Filter" button that opens a bottom sheet |
| Job detail description is full-width on mobile | Already single-column — just needs padding and max-width |
| Admin bulk bar wraps badly on mobile | Stack vertically, hide until selection made |
| Sign-in form has no brand context on mobile | Add a small logo + tagline above the form |

---

## 8. Accessibility Fixes (WCAG AA)

| Issue | Current | Fix |
|---|---|---|
| Body text contrast | `#666` on white = 5.7:1 (borderline) | Use `#374151` = 8.6:1 ✅ |
| Gray metadata text | `#999` on white = 2.8:1 ❌ | Use `#6B7280` = 4.6:1 ✅ |
| Focus rings | Bootstrap default (thin blue outline) | 3px indigo outline, 2px offset |
| Form labels | Visually hidden on sign-in (placeholder only) | Show labels above inputs |
| Icon-only buttons | No aria-label on language switcher | Add `aria-label` |
| Status color-only | Active/pending distinguished only by color | Add text label alongside dot |

---

## 9. Implementation Roadmap

Phased to minimize risk and deliver value incrementally. Treat the phases below as design intent; implementation now belongs in the current FastAPI + Next.js stack.

### Phase 1 — Design Tokens & Typography (1–2 days)
*Zero functional risk. Pure CSS changes.*

1. Update `client/lib/custom.bootstrap.less` — new color palette, border-radius, shadows
2. Update `client/lib/journal.variables.import.less` — spacing scale, font sizes
3. Fix body text color `#666` → `#374151`
4. Fix button border-radius `0px` → `6px`
5. Fix card border-radius `0px` → `8px`
6. Add card shadow, remove flat border
7. Fix OAuth button labels in `both/accounts.js` AccountsTemplates config

**Deliverable:** Every existing page looks noticeably more modern with zero template changes.

### Phase 2 — Navigation & Hero (2–3 days)
*Low risk. Template changes to header and home.*

1. Restyle `client/views/includes/header.html` + `header.less`
   - Add bottom border to navbar
   - Style "Post a Job" as a button
   - Language switcher → icon only
   - Mobile: bottom sheet nav
2. Restyle `client/views/home.html` jumbotron
   - Add `min-height`, trust bar, fix CTA hierarchy
   - Add job count reactive helper

**Deliverable:** First impression dramatically improved.

### Phase 3 — Job Cards & Listing (2–3 days)
*Medium risk. Template + helper changes.*

1. Redesign `client/views/jobs/jobSmall.html` — company avatar, pill badges, hover state
2. Redesign `client/views/jobs/jobs.html` — filter bar collapse on mobile, job count, empty state illustration
3. Add `client/views/jobs/jobEmpty.html` partial

**Deliverable:** Browsing experience feels like a real job board.

### Phase 4 — Job Detail (2–3 days)
*Medium risk. Layout restructure.*

1. Redesign `client/views/jobs/job.html`
   - Header band with company avatar
   - Two-column layout (description + sidebar)
   - Prominent apply/contact CTA
   - Sticky sidebar on desktop
   - Fixed apply button on mobile
2. Move featured upsell to sidebar, below apply CTA
3. Move admin controls to a collapsible panel (admin-only, not inline)

**Deliverable:** Job seekers can find the apply action immediately.

### Phase 5 — Post a Job Wizard (3–4 days)
*Higher risk. Form logic changes.*

1. Redesign `client/views/jobs/jobForms.html` + `jobForms.js`
   - 3-step wizard with progress bar
   - Step 1: basics, Step 2: content, Step 3: preview + submit
   - Plain textarea on mobile for description
   - Character counter
   - Fix submit button label
2. Add `client/views/jobs/jobFormStep.html` partials

**Deliverable:** Job posting completion rate improves. Mobile posting becomes possible.

### Phase 6 — Auth Pages (1–2 days)
*Low-medium risk. AccountsTemplates customisation.*

1. Create custom sign-in/sign-up templates (AccountsTemplates supports `customTemplates`)
2. Two-column layout, brand panel, OAuth button labels
3. Password show/hide toggle
4. Form labels visible

**Deliverable:** Auth pages feel like part of the product.

### Phase 7 — My Jobs & Account (1–2 days)
*Low risk. Template + helper changes.*

1. Redesign `client/views/jobs/jobs.html` (myJobs route)
   - Status badges, inline actions, status filter tabs, empty state
2. Redesign account page
   - Visual separation of danger zone (delete account)
   - Back navigation

### Phase 8 — Admin Panel (2–3 days)
*Medium risk. Template + subscription changes.*

1. Redesign `client/views/admin/adminJobs.html`
   - Sub-navigation tabs (Jobs / Reports / Admins)
   - Counts on all status tabs
   - Human-readable report reasons
   - Bulk bar hidden until selection
   - Compact job rows

---

## 10. What NOT to Change

- The legacy Meteor/Blaze/Bootstrap 3 stack — retained here only as historical context
- The URL structure (minor `/job` → `/jobs/new` is optional)
- The data model, publications, or methods
- The i18n system — it works well
- The reCAPTCHA integration
- The Stripe integration
- The multi-market subdomain architecture

---

## 11. Competitive Reference Points

These are not aspirational clones — they're reference points for specific patterns:

| Pattern | Reference |
|---|---|
| Job card with company avatar | LinkedIn Jobs, Wellfound |
| Two-column job detail | Greenhouse, Lever |
| 3-step post wizard | Airbnb host onboarding, Stripe Connect |
| Trust bar in hero | Stripe, Notion |
| Mobile filter bottom sheet | Airbnb, Booking.com |
| Admin compact rows with inline actions | Linear, Notion |

---

## 12. Success Metrics

After implementation, measure:

| Metric | Proxy | Target |
|---|---|---|
| Job posting completion rate | Jobs created / job form visits | +30% |
| Mobile job posting rate | Jobs created on mobile / total | +50% |
| Time to apply action | Seconds from job detail load to contact click | < 5s |
| Bounce rate on home | Analytics | -20% |
| Admin moderation time | Time per job reviewed | -40% (better UX) |
| WCAG AA compliance | Automated axe scan | 0 contrast failures |
