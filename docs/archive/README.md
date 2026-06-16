<!-- last_verified: 2026-06-15T00:00:00Z | git_ref: fix/quality-run-2026-06-10 | verified_by: self-contained cleanse 2026-06-15 -->

# Archived documentation

These documents are **historical reference only**. They describe the Meteor-era
codebase and the one-time migration to the current FastAPI + Next.js stack, or
superseded planning artefacts. None of them describe how the product works
today — for current state see `README.md`, `CLAUDE.md`, `SERVICES.md`, and
`docs/architecture/`.

| File | What it was | Why archived |
|------|-------------|--------------|
| `MIGRATION-PLAN.md` | Plan for migrating Meteor → FastAPI/Next.js | Migration is complete; the current stack is FastAPI + Next.js. |
| `REDESIGN.md` | UI/UX redesign plan during the migration | Superseded by the shipped frontend. |
| `meteor-3-package-audit.md` | Audit of Meteor 3 packages | The product no longer runs Meteor. |
| `FIXES_PLAN.md` | Large historical fix-planning document | Superseded by `docs/product/BACKLOG.md` + per-run quality artefacts. |
| `decisions/001-node-18-on-meteor-2.md` | ADR: Node 18 on Meteor 2 | Meteor-era; superseded. |
| `decisions/002-mongodb-not-postgres.md` | ADR: MongoDB over Postgres | Reversed — the product runs PostgreSQL. |
| `decisions/003-meteor-accounts-not-jwt.md` | ADR: Meteor accounts over JWT | Reversed — auth is JWT. |
| `decisions/004-bootstrap-5-phased-migration.md` | ADR: Bootstrap 5 phased migration | Meteor-era UI plan; superseded. |

Current, still-applicable ADRs remain in `docs/decisions/` (`005`, `006`).
