---
last_verified: 2026-06-27T00:00:00Z
git_ref: master
verified_by: prod documentation refresh
---

# On-Call & Alert Routing

## Current stack

| Layer | Tool | Status |
|-------|------|--------|
| Error tracking | Bugsink via `SENTRY_DSN` | SDKs are wired; DSN is empty, so events do not flow yet |
| Uptime monitoring | Gatus | Production checks are not wired yet |
| Backend health | `https://api.joinemployed.com/health` | returns API/DB/Redis status when healthy |
| Deployment | GitHub Actions + AWS OIDC + SSM Run Command | production backend deploy path |

## Recommended alerts

1. API health check fails for two consecutive intervals.
2. Frontend apex fails for two consecutive intervals.
3. Bugsink receives a new high-severity issue or an error-rate spike after DSNs are wired.
4. RDS CPU/storage/connection alarms breach thresholds.
5. AWS budget alerts reach configured tiers.

## Escalation

| Severity | Definition | Response |
|----------|------------|----------|
| P1 | frontend or API unavailable | immediate |
| P2 | auth, payments, email, or DB degraded | within 1 hour |
| P3 | non-critical feature issue | next business day |

## Setup TODO

- Assign primary and secondary on-call owners.
- Connect Gatus and Bugsink alerts to the chosen notification channel.
- Keep alert routing credentials outside the repo.
