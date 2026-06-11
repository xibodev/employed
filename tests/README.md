<!-- last_verified: 2026-06-11T02:02:49Z | git_ref: fix/quality-run-2026-06-10 | verified_by: doc-drift audit, quality run 2026-06-10_120309 -->

# Tests

Current test coverage for the FastAPI backend, the Next.js frontend, and Playwright E2E flows.

## Status

Meteor Mocha tests have been removed with the legacy application code. The active test surfaces are now:

- backend `pytest`
- frontend `npm run build`
- frontend `npm run typecheck`
- Playwright E2E under `tests/e2e/`

## Running

```bash
# Root lint
npm run lint

# Backend API tests
cd backend
python -m pytest

# Frontend verification
cd ..\frontend
npm run build
npm run typecheck

# E2E smoke / journeys (requires the app stack to be running)
cd ..
npx playwright test tests/e2e/
```

## Test files

### Backend

The backend pytest suite lives in `backend/tests/` (134 tests as of
`fix/quality-run-2026-06-10`) and covers:

- auth
- jobs
- market resolution
- rate limiting
- observability / health endpoints
- payments
- profiles
- public API
- users
- webhooks
- workers (job expiry)
- admin workflows

### E2E

Specs are locale-aware (assertions use the per-market catalogs via
`tests/e2e/i18n.js`; MZ defaults to `pt`, MX to `es`).

| File | What it covers |
| --- | --- |
| `tests/e2e/smoke.spec.js` | Cross-stack smoke coverage: health, public pages, robots/sitemap, core browse flows |
| `tests/e2e/journey-visitor.spec.js` | Anonymous visitor browse journey |
| `tests/e2e/journey-seeker.spec.js` | Job-seeker journey (register, verify, browse) |
| `tests/e2e/journey-employer.spec.js` | Employer journey (post job, my-jobs) |
| `tests/e2e/journey-admin.spec.js` | Admin moderation journey |
| `tests/e2e/journey-multiuser.spec.js` | Cross-persona interactions |

### Frontend

No unit/component tests yet (known gap TD-004) — coverage is build +
typecheck + ESLint plus the E2E suite above.

## CI

The repository CI now validates the backend and frontend separately, with browser automation reserved for UAT / E2E workflows.
