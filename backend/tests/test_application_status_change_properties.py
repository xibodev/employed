"""Property-based test for application status-change persistence.

# Feature: multi-tenant-hiring-platform, Property 21: Application status changes persist the new stage

Property 21 (design.md): *For any* application and any valid target pipeline
stage, changing the status updates the application to that stage.

The test drives :func:`app.services.applications.change_status` over a captured
fake session (mirroring ``tests/test_application_creation_properties.py``) so the
service's ``add``/``flush``/``execute`` run without a real Postgres database.
``Application`` uses Postgres-specific column types, so a fake session captures
the persistence calls; the guarded ``application.status_changed`` emission runs
as a harmless no-op because ``execute`` returns no subscribed endpoints.

For every generated initial status and target ``ApplicationStatus`` stage,
``change_status`` must leave the application at the target stage and append an
``AuditLog`` row capturing the before/after status (R17.3, R17.5).

Validates: Requirements 17.3
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from app.models.application import Application
from app.models.audit_log import AuditLog
from app.models.enums import ApplicationStatus
from app.services import applications


class _FakeResult:
    """Stand-in query result yielding no rows (no subscribed webhook endpoints)."""

    def scalars(self) -> "_FakeResult":
        return self

    def all(self) -> list[object]:
        return []


class _FakeSession:
    """Captured session recording add/flush; ``execute`` returns no rows.

    The captured ``execute`` lets the guarded ``application.status_changed``
    emission run as a harmless no-op (no endpoints) instead of touching a real
    database.
    """

    def __init__(self) -> None:
        self.added: list[object] = []
        self.flushed = 0

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        self.flushed += 1

    def execute(self, *args: object, **kwargs: object) -> _FakeResult:
        return _FakeResult()


_statuses = st.sampled_from(list(ApplicationStatus))


@settings(max_examples=100)
@given(initial_status=_statuses, target_status=_statuses)
def test_change_status_persists_new_stage(initial_status: ApplicationStatus, target_status: ApplicationStatus) -> None:
    db = _FakeSession()
    actor = SimpleNamespace(id=uuid4())

    # Build an Application at the generated initial stage via the ORM
    # constructor (mirrors the creation property test).
    application = Application(
        job_id=uuid4(),
        company_id=uuid4(),
        candidate_user_id=uuid4(),
        status=initial_status,
    )
    application.id = uuid4()

    result = applications.change_status(
        db,
        application=application,
        new_status=target_status,
        actor=actor,
    )

    # Property 21: the application is updated to the target stage (R17.3).
    assert application.status == target_status
    assert result is application

    # Persisted within the caller's transaction.
    assert application in db.added
    assert db.flushed >= 1

    # An append-only audit row captures the before/after status (R17.5).
    audit_rows = [obj for obj in db.added if isinstance(obj, AuditLog)]
    assert len(audit_rows) == 1
    entry = audit_rows[0]
    assert entry.target_type == "application"
    assert entry.target_id == application.id
    assert entry.before == {"status": initial_status.value}
    assert entry.after == {"status": target_status.value}
