# ADR-003: Meteor Accounts (not JWT)

**Status:** Superseded (2026-06-10) — the May 2026 rewrite replaced Meteor Accounts with JWT auth (access + refresh tokens, `backend/app/auth/`), ending the deferral (`MIGRATION-PLAN.md`). Kept as historical record.  
**Date:** Inherited from upstream  
**Context:** The portfolio standard (S-06) recommends JWT-based auth. Employed uses Meteor's built-in `accounts-password` package with DDP session tokens.  
**Decision:** Keep Meteor Accounts. JWT migration would require replacing the session transport, all `Meteor.userId()` calls, and the publication auth model — a major rewrite with no user-facing benefit.  
**Consequences:** Auth works but is tightly coupled to Meteor's DDP transport. OAuth providers (Google, GitHub) can still be added via `accounts-oauth`. Deferred until a broader Meteor 3 or framework migration.
