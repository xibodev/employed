from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import timedelta


def test_expire_old_jobs_records_status_history_reason(db_session, job_factory, monkeypatch):
    """EMP-017 regression: JobStatus has no 'expired' member so expiry maps
    to 'inactive' — the worker must record WHY in status_history so expired
    listings stay distinguishable from owner-deactivated ones."""
    from app.services.model_utils import utcnow
    from app.workers import tasks

    old_job = job_factory(status="active", created_at=utcnow() - timedelta(days=120))
    fresh_job = job_factory(status="active")

    @contextmanager
    def fake_session_scope():
        yield db_session

    monkeypatch.setattr(tasks, "session_scope", fake_session_scope)
    monkeypatch.setattr(tasks, "resolve_model", lambda name, aliases=None: type(old_job))

    expired_count = asyncio.run(tasks.expire_old_jobs({}))

    assert expired_count == 1
    db_session.refresh(old_job)
    db_session.refresh(fresh_job)
    assert old_job.status == "inactive"
    assert fresh_job.status == "active"
    last_entry = old_job.status_history[-1]
    assert last_entry["reason"] == "expired (90-day listing window)"
    assert last_entry["by"] == "worker:expire_old_jobs"
    assert last_entry["from"] == "active"
    assert old_job.expired_at is not None
