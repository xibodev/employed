---
last_verified: 2026-06-11T02:02:49Z
git_ref: fix/quality-run-2026-06-10 (uat baseline 00aa899)
verified_by: doc-drift audit, quality run 2026-06-10_120309
---

# Backup Strategy & Disaster Recovery

> employed.co.mz — PostgreSQL 16 on Box 3 (`109.123.241.71`)
>
> **Status: requires-verification.** This document defines the target
> procedure. Whether the backup cron and off-site sync are actually
> configured on Box 3 has NOT been verified — confirm on-box
> (`crontab -l`, `ls /backups`) before relying on it. Reference script:
> `backend/scripts/backup-db.sh`.

---

## 1. Data Classification

| Store | RPO | RTO | Notes |
|-------|-----|-----|-------|
| PostgreSQL (jobs, users, payment_intents, reports, profiles) | 1 hour | 4 hours | Primary business data — Docker volume `postgres_data` |
| Stripe event log | N/A | N/A | Stripe retains this; webhook replay available via Stripe dashboard |
| Redis | N/A | Minutes | Ephemeral queue/limits/revocation — no backup needed (TTL-bounded by design) |

---

## 2. Backup Schedule

### PostgreSQL — `pg_dump`

```bash
# Runs via cron on Box 3 (or a sidecar container)
# Every 6 hours — matches RPO target of 1 hour with margin
0 */6 * * * docker exec employed-postgres-1 \
  pg_dump -U employed -d employed --format=custom \
  > /backups/employed-$(date +%Y%m%d-%H%M).dump \
  2>> /var/log/backup.log
```

Or using `docker compose exec`:

```bash
docker compose -f /opt/employed/docker-compose.yml exec -T postgres \
  pg_dump -U employed -d employed --format=custom \
  > /backups/employed-$(date +%Y%m%d-%H%M).dump
```

### Retention

| Window | Frequency | Copies |
|--------|-----------|--------|
| Last 48 hours | Every 6 hours | 8 |
| Last 30 days | Daily (midnight) | 30 |
| Last 12 months | Monthly (1st) | 12 |

Old backups are pruned by a `find /backups -mtime +N -delete` cron.

### Off-site Copy

```bash
# Example: rclone to Backblaze B2 or any S3-compatible store
rclone copy /backups/employed-*.dump b2:employed-backups/daily/ --max-age 24h
```

---

## 3. Restore Procedure

### Full Restore

```bash
# Stop the application but keep postgres running
docker compose stop backend frontend worker

# Restore from backup
docker compose exec -T postgres \
  pg_restore -U employed -d employed --clean --if-exists \
  < /backups/employed-YYYYMMDD-HHMM.dump

# Restart
docker compose start backend frontend worker
```

### Point-in-Time (WAL archiving)

Not currently configured. To enable, set `wal_level=replica` and configure `archive_command` in PostgreSQL.

---

## 4. Verification

- **Weekly**: dry-run restore to a throwaway container
- **Monthly**: manual restore to a staging instance, verify row counts

```bash
# Quick sanity check after restore
docker compose exec postgres psql -U employed -d employed -c "
  SELECT
    (SELECT count(*) FROM jobs) AS jobs,
    (SELECT count(*) FROM users) AS users,
    (SELECT count(*) FROM payment_intents) AS payment_intents;
"
```

---

## 5. Disaster Recovery Runbook

| Scenario | Action | Owner |
|----------|--------|-------|
| Database corruption | Restore from latest 6h backup | Ops |
| Server loss | Re-deploy from GHCR images + restore DB from off-site backup | Ops |
| Region outage | Spin up new VPS, `docker compose up`, restore DB, update DNS | Ops |
| Accidental data deletion | Restore specific tables from backup into staging, copy rows | Ops + Dev |

### Recovery Steps

1. Identify scope (which tables? how recent?)
2. Find most recent clean backup (`ls -lt /backups/`)
3. Stop the application (`docker compose stop backend frontend worker`)
4. Restore with `pg_restore` (see above)
5. Verify row counts and spot-check recent records
6. Restart (`docker compose start backend frontend worker`)
7. Check `https://api.employed.xibodev.com/health` returns `"status":"ok"`
8. Monitor logs for error spikes: `docker compose logs -f --tail=50 backend`

---

## 6. Monitoring

- Backup cron failures → alert via UptimeRobot heartbeat (ping the heartbeat URL at the end of the cron script)
- Disk space on Box 3 → alert at 80% capacity (`df -h /`)
- Off-site sync failures → check `rclone` exit code in cron log
