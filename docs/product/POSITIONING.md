# Employed — Product Positioning

```yaml
last_verified: 2026-06-28T00:00:00Z
git_ref: master
verified_by: prod documentation refresh
```

## One line

Employed is more than a job board and less than a heavy ATS: a trust-centric, integration-ready hiring platform for localized markets.

## Current product

Employed serves Mozambique and Mexico from `joinemployed.com`. The platform combines localized job listings with company management, memberships, permission-based RBAC, verification badges, JSON Resume profiles, an application pipeline, audit logs, webhooks, and export APIs.

## Differentiators

1. **Trust.** Companies, jobs, and profiles use a shared verification state machine and composable badges instead of a single opaque score.
2. **Portability.** JSON Resume, schema.org `JobPosting`, normalized Application objects, `external_refs`, webhooks, and `/export/v1` keep the platform integration-ready.
3. **Localized simplicity.** Market, locale, pricing, and payment providers come from hostnames while tenant permissions remain company-scoped.

## Boundaries

- Not a full ATS: the pipeline is intentionally lightweight.
- Not single-tenant: companies and memberships are first-class.
- Not a lock-in system: data export and webhooks are core product surfaces.

## Markets

- `joinemployed.com` and `mz.joinemployed.com`: MZ, default `pt`.
- `mx.joinemployed.com`: MX, default `es`.
- Supported locale codes: `en`, `pt`, `es`.
