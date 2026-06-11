---
last_verified: 2026-06-11T02:02:49Z
git_ref: fix/quality-run-2026-06-10 (uat baseline 00aa899)
verified_by: doc-drift audit, quality run 2026-06-10_120309
---

# PostgreSQL Backup & Restore Procedure

> docs/operations/postgres-backup.md — P-013
>
> **Status: requires-verification.** Target procedure; the cron and off-site
> sync are not confirmed configured on Box 3. See also `docs/backup-strategy.md`.

---

## Overview

Employed uses a single PostgreSQL instance (compose service `postgres`,
container `employed-postgres-1` on Box 3) in the product compose stack.
Backups are taken with `pg_dump` and stored in object storage (S3-compatible).

---

## Backup Schedule

| Type | Frequency | Retention | Tool |
|------|-----------|-----------|------|
| Full logical dump | Daily at 02:00 UTC | 14 days | `pg_dump` + cron |
| Weekly archive | Every Sunday at 02:30 UTC | 90 days | Copy of daily dump |
| Pre-deployment snapshot | Before each deploy | 7 days | `pg_dump` in deploy script |

---

## Manual Backup

```bash
# Run inside the db container (or on the host with DB access)
docker exec employed-postgres-1 \
  pg_dump -U "${POSTGRES_USER}" "${POSTGRES_DB}" \
  | gzip \
  > "/backups/employed_$(date +%Y%m%dT%H%M%S).sql.gz"
```

Required env vars: `POSTGRES_USER`, `POSTGRES_DB`.

---

## Automated Backup Cron (example)

```bash
# /etc/cron.d/employed-pg-backup
0 2 * * * root /opt/employed/scripts/backup-db.sh >> /var/log/employed-backup.log 2>&1
```

See `backend/scripts/backup-db.sh` for the reference implementation.

---

## Verify a Backup

```bash
# List dumps
ls -lh /backups/*.sql.gz

# Inspect without restoring
zcat /backups/employed_20260101T020000.sql.gz | head -40
```

---

## Restore Procedure

### 1. Stop application traffic

```bash
docker compose -f deploy/docker-compose.prod.yml stop backend worker
```

### 2. Create a safety snapshot of the current database

```bash
docker exec employed-postgres-1 \
  pg_dump -U "${POSTGRES_USER}" "${POSTGRES_DB}" \
  | gzip > "/backups/pre-restore-safety-$(date +%Y%m%dT%H%M%S).sql.gz"
```

### 3. Restore from dump

```bash
# Drop and recreate the target database
docker exec -i employed-postgres-1 psql -U "${POSTGRES_USER}" -c \
  "DROP DATABASE IF EXISTS \"${POSTGRES_DB}\"; CREATE DATABASE \"${POSTGRES_DB}\";"

# Restore
zcat /backups/employed_<TIMESTAMP>.sql.gz \
  | docker exec -i employed-postgres-1 \
    psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"
```

### 4. Run Alembic migrations (if restoring to an older schema version)

```bash
docker compose -f deploy/docker-compose.prod.yml run --rm migrate
```

### 5. Restart services

```bash
docker compose -f deploy/docker-compose.prod.yml up -d backend worker
```

---

## Point-in-Time Recovery (future)

When the database grows to a scale where WAL archiving is justified, enable
`wal_level = replica` and `archive_mode = on` in PostgreSQL config, and configure
`archive_command` to push WAL segments to object storage. This allows PITR restores
with `pg_basebackup` + WAL replay.

---

## Off-site Storage

Upload dumps to the configured S3-compatible bucket:

```bash
aws s3 cp /backups/employed_<TIMESTAMP>.sql.gz \
  "s3://${BACKUP_BUCKET}/postgres/employed_<TIMESTAMP>.sql.gz" \
  --sse AES256
```

Required env vars: `BACKUP_BUCKET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`,
`AWS_DEFAULT_REGION` (or equivalent for the chosen object-storage provider).

---

## Testing Restores

Test restores should be performed monthly against a staging database:

1. Pull the latest dump from off-site storage.
2. Restore to a staging Postgres instance (`employed_staging`).
3. Run the full test suite against staging: `cd backend && python -m pytest`.
4. Confirm the restore succeeded and record the result in the ops log.

---

## Contacts

See `docs/operations/oncall.md` for escalation contacts.
