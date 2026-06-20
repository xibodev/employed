# Feature: multi-tenant-hiring-platform, Property 19: Domain-event emission never rolls back the triggering write
"""Property-based tests for Property 19 (R16.7).

Property 19: *For any* application creation or status change, a failure while
emitting the associated webhook event leaves the application (and its new
status) persisted.

The application service emits the ``application.created`` /
``application.status_changed`` webhook events *after* the row has been added and
flushed, through guarded ``_emit_*`` helpers that swallow emission errors. These
tests drive ``create_application`` and ``change_status`` with a captured session
(recording ``add``/``flush`` in the spirit of ``tests/test_audit_service.py``)
while ``app.services.webhooks.emit`` is patched to raise, and assert the write is
retained and the exception never propagates.

**Validates: Requirements 16.7**
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.models.application import Application
from app.models.enums import ApplicationStatus
from app.services import applications


class _CapturedSession:
    """Minimal Session stand-in recording add/flush (see test_audit_service)."""

    def __init__(self) -> None:
        self.added: list[object] = []
        self.flushes = 0

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        self.flushes += 1


class _EmitBoom(RuntimeError):
    """Raised by the patched ``emit`` to simulate an emission failure."""


def _raising_emit(*_args: object, **_kwargs: object) -> None:
    raise _EmitBoom("webhook emission failed")


PBT_SETTINGS = settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)

# One candidate reference exactly: either a platform user id or an inline snapshot.
candidate_refs = st.one_of(
    st.builds(lambda uid: {"candidate_user_id": uid, "candidate_snapshot": None}, st.uuids()),
    st.builds(
        lambda name: {"candidate_user_id": None, "candidate_snapshot": {"name": name}},
        st.text(min_size=0, max_size=40),
    ),
)


@PBT_SETTINGS
@given(
    job_id=st.uuids(),
    candidate=candidate_refs,
    source=st.text(min_size=1, max_size=32),
)
def test_create_application_emission_failure_retains_write(
    job_id: object,
    candidate: dict,
    source: str,
) -> None:
    """create_application keeps the persisted application when emission fails."""
    db = _CapturedSession()

    # Patch the lazily-imported emit so the guarded helper hits a failure path.
    with patch("app.services.webhooks.emit", side_effect=_raising_emit):
        application = applications.create_application(
            db,  # type: ignore[arg-type]
            job_id=job_id,  # type: ignore[arg-type]
            candidate_user_id=candidate["candidate_user_id"],
            candidate_snapshot=candidate["candidate_snapshot"],
            source=source,
        )

    # The exception did not propagate (we reached here) and the row is retained.
    assert isinstance(application, Application)
    assert application in db.added
    assert db.flushes >= 1
    # Created at the first pipeline stage and that status is retained.
    assert application.status == ApplicationStatus.applied


@PBT_SETTINGS
@given(
    job_id=st.uuids(),
    candidate=candidate_refs,
    initial_status=st.sampled_from(list(ApplicationStatus)),
    new_status=st.sampled_from(list(ApplicationStatus)),
)
def test_change_status_emission_failure_retains_new_stage(
    job_id: object,
    candidate: dict,
    initial_status: ApplicationStatus,
    new_status: ApplicationStatus,
) -> None:
    """change_status keeps the new pipeline stage when emission fails."""
    db = _CapturedSession()
    actor = SimpleNamespace(id=uuid4())

    application = Application(
        job_id=job_id,
        candidate_user_id=candidate["candidate_user_id"],
        candidate_snapshot=candidate["candidate_snapshot"],
        status=initial_status,
    )

    with patch("app.services.webhooks.emit", side_effect=_raising_emit):
        result = applications.change_status(
            db,  # type: ignore[arg-type]
            application=application,
            new_status=new_status,
            actor=actor,  # type: ignore[arg-type]
        )

    # The exception did not propagate and the new stage is persisted.
    assert result is application
    assert application.status == new_status
    assert application in db.added
    assert db.flushes >= 1
