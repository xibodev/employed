# Feature: multi-tenant-hiring-platform, Property 17: Tracked applications start in the applied stage
"""Property-based tests for tracked-application creation (R16).

Property 17 (design.md): *For any* tracked application submission, the created
application has status ``applied`` and carries exactly one candidate reference
(either a candidate user id or a profile snapshot).

**Validates: Requirements 16.2, 16.4**
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.models.enums import ApplicationStatus
from app.services import applications


class _FakeSession:
    """Minimal stand-in for a SQLAlchemy Session capturing add/flush calls.

    ``Application`` is a Postgres-typed model, so the tests avoid a real engine
    and instead record the persistence calls the service makes.
    """

    def __init__(self) -> None:
        self.added: list[object] = []
        self.flushed = 0

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        self.flushed += 1


# A snapshot is any non-empty JSON-ish object; only its presence matters for R16.2.
_snapshots = st.dictionaries(
    st.text(min_size=1, max_size=12),
    st.one_of(st.text(max_size=24), st.integers(), st.booleans()),
    min_size=1,
    max_size=5,
)


@st.composite
def _single_candidate_reference(draw: st.DrawFn) -> dict[str, object]:
    """Generate exactly one candidate reference (R16.2): user id XOR snapshot."""
    if draw(st.booleans()):
        return {"candidate_user_id": draw(st.uuids()), "candidate_snapshot": None}
    return {"candidate_user_id": None, "candidate_snapshot": draw(_snapshots)}


@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(job_id=st.uuids(), ref=_single_candidate_reference())
def test_property_17_created_application_is_applied_with_one_reference(
    monkeypatch: pytest.MonkeyPatch,
    job_id: object,
    ref: dict[str, object],
) -> None:
    """Property 17: a tracked submission yields an ``applied`` application that
    carries exactly the one supplied candidate reference (the other is None).

    **Validates: Requirements 16.2, 16.4**
    """
    # Keep the test isolated from webhook enqueue side effects (R16.6/16.7).
    monkeypatch.setattr(applications, "_emit_application_created", lambda db, application: None)

    db = _FakeSession()
    application = applications.create_application(
        db,
        job_id=job_id,
        candidate_user_id=ref["candidate_user_id"],
        candidate_snapshot=ref["candidate_snapshot"],
    )

    # R16.4: created at the first pipeline stage.
    assert application.status is ApplicationStatus.applied

    # R16.2: exactly one candidate reference is carried.
    assert (application.candidate_user_id is None) != (application.candidate_snapshot is None)
    if ref["candidate_user_id"] is not None:
        assert application.candidate_user_id == ref["candidate_user_id"]
        assert application.candidate_snapshot is None
    else:
        assert application.candidate_snapshot == ref["candidate_snapshot"]
        assert application.candidate_user_id is None

    # The application is persisted within the caller's transaction (DD-10).
    assert db.added == [application]
    assert db.flushed == 1


@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(job_id=st.uuids(), snapshot=_snapshots, user_id=st.uuids())
def test_property_17_ambiguous_reference_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    job_id: object,
    snapshot: dict[str, object],
    user_id: object,
) -> None:
    """R16.2: supplying both candidate references or neither raises ValueError,
    and nothing is persisted.

    **Validates: Requirements 16.2**
    """
    monkeypatch.setattr(applications, "_emit_application_created", lambda db, application: None)

    # Both references present -> ambiguous.
    db_both = _FakeSession()
    with pytest.raises(ValueError):
        applications.create_application(
            db_both,
            job_id=job_id,
            candidate_user_id=user_id,
            candidate_snapshot=snapshot,
        )
    assert db_both.added == []
    assert db_both.flushed == 0

    # Neither reference present -> missing.
    db_neither = _FakeSession()
    with pytest.raises(ValueError):
        applications.create_application(
            db_neither,
            job_id=job_id,
            candidate_user_id=None,
            candidate_snapshot=None,
        )
    assert db_neither.added == []
    assert db_neither.flushed == 0
