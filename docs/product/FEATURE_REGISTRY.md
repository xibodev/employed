# Employed — Feature Registry

```yaml
last_verified: 2026-06-28T00:00:00Z
git_ref: master
verified_by: prod documentation refresh
```

Statuses use: `planned`, `in_progress`, `implemented`, `tested_locally`, `uat_ready`, `deployed_to_uat`, `blocked`, `deprecated`.

## Product features

| ID | Feature | Status | Evidence |
|----|---------|--------|----------|
| EMP-F-001 | Market-localized listings for MZ/MX hosts | `deployed_to_uat` | Production hosts `joinemployed.com`, `mz.joinemployed.com`, `mx.joinemployed.com` route to the same Vercel frontend and derive market by hostname |
| EMP-F-002 | Email/password auth and Google OAuth | `deployed_to_uat` | Backend auth routers and Google callback are deployed behind `api.joinemployed.com` |
| EMP-F-003 | Company entities and memberships | `deployed_to_uat` | Models/services/routers and frontend company surfaces are in the production branch |
| EMP-F-004 | Two-layer permission RBAC | `deployed_to_uat` | `services/rbac.py` permission catalog and `require_permission` gates are in the production branch |
| EMP-F-005 | Verification state machine and trust badges | `deployed_to_uat` | Shared verification/trust services are in the production branch |
| EMP-F-006 | Application pipeline | `deployed_to_uat` | Application model/services/routers and list/kanban UI are in the production branch |
| EMP-F-007 | JSON Resume profiles and profile versions | `deployed_to_uat` | Profile versioning services and export surfaces are in the production branch |
| EMP-F-008 | Append-only audit log | `deployed_to_uat` | Audit model/service and update guards are in the production branch |
| EMP-F-009 | Outbound webhooks | `deployed_to_uat` | Webhook admin routes, delivery tasks, and bounded retry constants are in the production branch |
| EMP-F-010 | Versioned export API | `deployed_to_uat` | `/export/v1` mappers and routes are in the production branch |
| EMP-F-011 | Stripe featured-listing payments | `deployed_to_uat` | Stripe adapter and test-mode webhook are configured |
| EMP-F-012 | M-Pesa/e-Mola payment options | `implemented` | Simulator adapters are present; real provider mode is not active |
| EMP-F-013 | AWS production deployment | `deployed_to_uat` | CDK stacks, ECR image, EC2 Compose runtime, RDS, and Vercel production frontend are current topology |
| EMP-F-014 | Bugsink error tracking | `live` | Project `employed-api` at errors.xibodev.com; backend DSN set, env production |
| EMP-F-015 | Gatus uptime monitoring | `live` | Monitors apex, market hosts, and API health |
| EMP-F-016 | Durable resume storage | `implemented` | Resume PDFs persist to R2 bucket `employed-prod-resumes`; user-facing download route is backlog |

## Status rules

- `deployed_to_uat` means the feature is present in the deployable production branch and belongs to the live product surface.
- `live` means the feature is wired and operating in production.
- `implemented` means the code path exists and is exercised, even if a downstream surface is still backlog.
- `blocked` names an external or operator dependency.
- `planned` names work with no committed implementation.
