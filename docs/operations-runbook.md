---
last_verified: 2026-06-28T00:00:00Z
git_ref: master
verified_by: prod documentation refresh
---

# Operations Runbook

Incident response and operational procedures for Employed production.

## Health checks

```bash
curl -fsS https://api.joinemployed.com/health
curl -fsS https://joinemployed.com/api/health
```

Backend healthy response:

```json
{ "status": "ok", "db": "ok", "redis": "ok" }
```

## Production runtime

- Frontend: Vercel project `selo-pro/employed`.
- API/worker/redis/cloudflared: Docker Compose on AWS EC2.
- Database: RDS PostgreSQL 17.
- Ingress: Cloudflare Tunnel for `api.joinemployed.com`.
- Secrets: SSM SecureStrings under `/employed/prod/*`.

## Log triage

Use AWS Systems Manager Session Manager or SSM Run Command to inspect the EC2 host. On the instance, the Compose project lives under `/opt/employed`.

```bash
cd /opt/employed
docker compose ps
docker compose logs --tail=100 api
docker compose logs --tail=100 worker
docker compose logs --tail=100 cloudflared
```

## Common incidents

| Symptom | First checks | Likely action |
|---------|--------------|---------------|
| API health fails | Compose status, `api` logs, RDS reachability | restart `api`; verify `DATABASE_URL`; inspect RDS status |
| DB degraded | RDS console/status, security group, credentials in SSM | restore connectivity; avoid deleting protected DB |
| Redis degraded | Compose `redis` logs | restart `redis`; queues/rate-limit state is ephemeral |
| API host unreachable | `cloudflared` logs and Cloudflare Tunnel status | restart `cloudflared`; verify tunnel token in SSM |
| Email failures | SES sending status, SMTP parameters in SSM | verify SES identity/SMTP creds |
| Stripe webhook failures | Stripe dashboard event logs and `STRIPE_WEBHOOK_SECRET` | verify endpoint and secret |

## Deploy and rollback

Backend deployment uses `.github/workflows/deploy-prod.yml`. Rollback selects a prior ECR `prod-<sha>` tag and reruns the EC2 deploy path. Frontend rollback uses Vercel deployment rollback or redeploy of a prior commit/tag.

## Severity

| Level | Definition | Target response |
|-------|------------|-----------------|
| P1 | `api.joinemployed.com/health` down or frontend unavailable | immediate |
| P2 | auth, payments, email, or database degraded | < 1 hour |
| P3 | non-critical feature or cosmetic issue | next business day |

## Post-incident

Record the cause, affected hosts, recovery action, and follow-up item in the appropriate operational tracker. Keep fixed docs present-tense; incident narrative belongs in release notes or logs.
