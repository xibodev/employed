# ADR-004: Bootstrap 5 phased migration

**Status:** Superseded (2026-06-10) — PR 3 never shipped; the May 2026 rewrite replaced the Blaze/Bootstrap UI with Next.js + Tailwind CSS, making the migration moot (`MIGRATION-PLAN.md`). Kept as historical record.  
**Date:** May 2026  
**Context:** The app shipped with Bootstrap 3 (EOL July 2019) and Font Awesome 4. A single-PR migration would be too risky — the visual diff touches every template and the `useraccounts:bootstrap` package has no BS5 equivalent.  
**Decision:** Split the migration into three PRs:
1. **PR 1 — Foundation:** Install BS5 via npm, stage SCSS overrides in `imports/styles/` (inert until activated). Complete.
2. **PR 2 — useraccounts replacement:** Hand-roll auth templates, remove `useraccounts:bootstrap`. Complete (A9.32).
3. **PR 3 — Template sweep:** Mechanical class renames across all templates, remove BS3 packages. Pending.

**Consequences:** The app currently runs BS3 with the new brand colours applied via LESS variable overrides. BS5 accessibility and modern patterns aren't available until PR 3 ships. The staged approach lets us ship the visual rebrand independently of the framework swap.

**Canonical tracker:** `brand/BS5-MIGRATION.md`
