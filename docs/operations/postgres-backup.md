---
last_verified: 2026-06-28T00:00:00Z
git_ref: master
verified_by: prod documentation refresh
---

# PostgreSQL Backup & Restore Procedure

Employed production uses RDS PostgreSQL 17. The instance is private, encrypted, and deletion-protected.

## Backup posture

RDS automated backups and snapshots are the primary backup mechanism. Confirm the configured retention window in AWS before relying on the RPO. Logical `pg_dump` exports are optional operator-controlled snapshots for migrations, audits, or point-in-time evidence.

## Manual logical backup

Run from an environment with network access to the private RDS endpoint and a `DATABASE_URL` resolved from SSM:

```bash
pg_dump "$DATABASE_URL" --format=custom --file employed-$(date +%Y%m%dT%H%M%S).dump
```

Store manual dumps in an approved encrypted location. Do not commit dumps.

## Restore outline

1. Stop application writes or put the app in maintenance mode.
2. Take a final safety snapshot.
3. Restore an RDS snapshot to a new instance or restore a logical dump to a prepared database.
4. Run `alembic upgrade head`.
5. Point `DATABASE_URL` to the restored database through SSM only after validation.
6. Run health checks and read-only smoke tests.

## Validation

After restore, verify row counts for users, jobs, companies, applications, payment intents, audit logs, and profile versions. Confirm `/health` returns `db: ok` and `redis: ok`.

## Redis

Redis is a sidecar cache/queue/state service. It is intentionally ephemeral and is not backed up.
