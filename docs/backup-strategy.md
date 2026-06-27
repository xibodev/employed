---
last_verified: 2026-06-27T00:00:00Z
git_ref: master
verified_by: prod documentation refresh
---

# Backup Strategy & Disaster Recovery

## Data classification

| Store | Backup strategy | Notes |
|-------|-----------------|-------|
| RDS PostgreSQL 17 | RDS automated backups/snapshots; optional encrypted logical dumps | Primary business data |
| Redis sidecar | no backup | Queue/rate-limit/revocation/replay state is ephemeral |
| Resume artifacts | no durable backup | Local EC2 artifacts are ephemeral until persistent media is added |
| Stripe events | provider retained | Use Stripe dashboard/API for replay/evidence |
| Deploy assets bucket | reproducible from repo | Used only for deployment plumbing |

## RPO/RTO targets

| Component | Target |
|-----------|--------|
| PostgreSQL RPO | governed by RDS backup retention and snapshot cadence |
| PostgreSQL RTO | restore to a new RDS instance and redeploy within the agreed incident window |
| EC2 runtime | rebuildable from CDK, ECR image, SSM parameters, and `deploy/ec2/` assets |
| Frontend | rollback/redeploy through Vercel |

## Disaster recovery outline

1. Identify failing surface: Vercel, Cloudflare Tunnel, EC2, RDS, SSM, or external provider.
2. Preserve evidence and avoid destructive actions against the protected RDS instance.
3. For EC2 loss, redeploy `Employed-Compute-prod`, rerun the production deploy workflow, and confirm Cloudflare Tunnel health.
4. For database loss/corruption, restore an RDS snapshot to a new instance, validate, update SSM `DATABASE_URL`, redeploy, and smoke test.
5. For frontend regression, rollback in Vercel or redeploy a prior commit/tag.

## Verification

Perform periodic restore drills using a non-production database target. Record results in operations notes or release notes, not in fixed architecture docs.
