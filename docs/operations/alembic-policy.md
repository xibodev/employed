---
last_verified: 2026-06-27T00:00:00Z
git_ref: master
verified_by: doc-drift audit, quality run 2026-06-10_120309 (ruff exclude confirmed in backend/pyproject.toml)
---

# Alembic Migration Immutability Policy

> P-NEW-005 — once-applied Alembic migrations must NEVER be reformatted in
> place. The on-disk representation is part of the deployment audit trail.

## Rules

1. **Never re-format an applied migration.** `ruff format` and `black` are
   configured to skip `backend/alembic/versions/` (`exclude` in
   `backend/pyproject.toml`).
2. **Never edit a migration after it has run in any environment** (dev,
   UAT, or production). If a fix is required, write a NEW migration that
   compensates for the previous one.
3. **Never delete a migration file.** Deletion breaks `alembic upgrade head`
   for any environment still on the older revision and orphans the
   `down_revision` chain.

## When you really need to change one

- It has not run anywhere yet — including local dev. Confirm with
  `alembic current` on every environment.
- The change is purely cosmetic (a docstring or comment fix that does not
  alter `op.*` calls) and you are absolutely certain no checksum-based
  drift detection compares the file bytes.

## Why

Some deploy tooling (and the GitHub Actions UAT release flow used by this
repo) hashes the migration file contents to detect tampering. A formatter
running over a folder of applied migrations changes those checksums and
makes the deploy gate think the schema is unverifiable.

## See also

- `backend/pyproject.toml` `[tool.ruff].exclude`
- `backend/alembic/versions/`
