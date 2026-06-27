---
last_verified: 2026-06-27T00:00:00Z
git_ref: master
verified_by: prod documentation refresh
---

# Architecture Overview — Employed

Employed is a multi-tenant, trust-centric hiring platform for MZ and MX. It combines localized job listings with companies, memberships, two-layer RBAC, verification workflows, JSON Resume profiles, applications, audit logs, webhooks, and export APIs.

## System shape

```text
browser
  ├─ joinemployed.com / www / mz / mx ──► Vercel Next.js frontend
  │                                           └─ API calls to api.joinemployed.com
  └─ api.joinemployed.com ──► Cloudflare Tunnel ──► EC2 Docker Compose
                                                        ├─ FastAPI api
                                                        ├─ arq worker
                                                        ├─ Redis sidecar
                                                        └─ cloudflared
                                                              │
                                                              ▼
                                                        RDS PostgreSQL 17
```

## Core invariants

- Market comes from hostname: `mx.*` → MX, `mz.*` and apex → MZ.
- Tenant comes from company membership and resource scope, not hostname.
- Authorization uses atomic permissions resolved across platform and tenant layers.
- Verification transitions go through a shared state machine and write audit rows.
- `AuditLog` and `ProfileVersion` are append-only.
- Background work uses arq.
- Export boundaries use standard schemas and versioned paths.

## Production infrastructure

Production runs in AWS account `868216907752`, region `us-east-1`, inside a CDK-managed VPC. The frontend is Vercel. The API is a Docker Compose workload on one EC2 Graviton instance reached through Cloudflare Tunnel. Data lives in RDS PostgreSQL 17. Redis is a sidecar, not a managed service. Secrets are SSM SecureStrings.

## Application modules

- `backend/app/routers/`: auth, jobs, profiles, payments, admin, companies, memberships, applications, verification, webhooks, export.
- `backend/app/services/`: RBAC, companies, memberships, verification, trust, applications, webhooks, export, email, payments support.
- `backend/app/models/`: users, jobs, profiles, companies, memberships, applications, audit logs, profile versions, webhooks, payment intents.
- `frontend/src/`: App Router pages, tenant context, API client, market helpers, auth context, UI components.

## Data and migrations

PostgreSQL is the system of record. Alembic migrations `001`-`005` are append-only and cover the initial schema, auth hardening, RBAC/tenancy, admin migration, and legacy profile/job migration.

## External integrations

AWS SES sends transactional email. Stripe is configured in test mode. M-Pesa and e-Mola are simulator-mode. Google OAuth and reCAPTCHA v3 are configured for `joinemployed.com`. Bugsink and Gatus are the observability standards; production wiring remains an operational follow-up.
