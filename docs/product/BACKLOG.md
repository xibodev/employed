# Employed — Backlog

```yaml
last_verified: 2026-06-27T00:00:00Z
git_ref: master
verified_by: prod documentation refresh
```

Actionable open items only.

## Production operations

| ID | Item | Status | Owner |
|----|------|--------|-------|
| BL-OPS-001 | Wire Bugsink DSNs for `employed-api` and `employed-web`; set `SENTRY_ENVIRONMENT=production` | `blocked` | operator |
| BL-OPS-002 | Add Gatus uptime checks for apex, market hosts, and API health | `planned` | operator |
| BL-OPS-003 | Confirm Google OAuth and reCAPTCHA allowed origins include market hosts if direct auth/submission happens on `mx` or `mz` | `planned` | operator |
| BL-OPS-004 | Replace Stripe test keys with live keys and verify live webhook when monetisation starts | `planned` | operator |
| BL-OPS-005 | Choose persistent storage for resume artifacts when durable PDFs are required | `planned` | product/operator |
| BL-OPS-006 | Confirm M-Pesa/e-Mola sandbox or live credentials before real mobile-money processing | `planned` | operator |

## Engineering

| ID | Item | Status | Owner |
|----|------|--------|-------|
| BL-ENG-001 | Add frontend component tests for company, membership, and applications views | `planned` | engineering |
| BL-ENG-002 | Pin or choose an HTML-to-PDF engine for enhanced resume PDFs | `planned` | engineering |
| BL-ENG-003 | Add restore-drill evidence for RDS backups in the operations tracker | `planned` | operator |
| BL-ENG-004 | Keep migrations append-only after `001`-`005` | `planned` | engineering |

## Done / no longer open

- Multi-tenant hiring platform implementation is complete.
- Production AWS launch is complete.
- Production Vercel frontend launch is complete.
- ECR SHA-tagged production images exist.
- The old shared-VPS UAT pipeline is disabled.
