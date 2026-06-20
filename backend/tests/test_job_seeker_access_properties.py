"""Property-based test for job-seeker access without a company membership.

# Feature: multi-tenant-hiring-platform, Property 25: Job seekers can browse and apply without a membership

Property 25 (design.md): *For any* authenticated user holding no company
membership, browsing published jobs and submitting an application both succeed.

Browsing is exercised through :func:`app.routers.jobs._apply_filters`, the
DB-free public listing filter. It takes no viewer/membership argument at all, so
its result depends only on the jobs and the active market -- never on whether the
viewer holds a membership. We additionally assert that a user with no membership
has an empty effective-permission set (via :func:`app.services.rbac.effective_permissions`
over a captured session that returns no membership rows) yet browsing still
returns the active, in-market jobs: browsing is not permission-gated (R12.1).

Applying is exercised through :func:`app.services.applications.create_application`
driven over a captured fake session (mirroring
``tests/test_application_creation_properties.py``). The service never consults
memberships, so an application submitted by a job seeker with no membership is
persisted at status ``applied`` (R12.2).

Validates: Requirements 12.1, 12.2
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from app.models.application import Application
from app.models.enums import ApplicationStatus
from app.routers.jobs import _apply_filters
from app.services import applications
from app.services.rbac import effective_permissions

# Markets the platform serves; a job's country is one of these (steering/product).
_MARKETS = ("MZ", "MX")
_JOB_STATUSES = ("pending", "active", "flagged", "inactive", "filled")


class _FakeResult:
    """Stand-in query result yielding no rows (no subscribed webhook endpoints)."""

    def scalars(self) -> "_FakeResult":
        return self

    def all(self) -> list[object]:
        return []


class _NoMembershipQuery:
    """Captured query whose ``filter(...).first()`` always returns ``None``.

    Models a job seeker with no Membership rows: every tenant-permission lookup
    in ``rbac.effective_permissions`` resolves to no active membership.
    """

    def filter(self, *args: object, **kwargs: object) -> "_NoMembershipQuery":
        return self

    def first(self) -> None:
        return None


class _FakeSession:
    """Captured session: records add/flush, returns no membership / webhook rows.

    ``query`` powers ``rbac`` membership lookups (always empty) and ``execute``
    lets the guarded ``application.created`` emission run as a harmless no-op
    instead of touching a real database.
    """

    def __init__(self) -> None:
        self.added: list[object] = []
        self.flushed = 0

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        self.flushed += 1

    def query(self, *args: object, **kwargs: object) -> _NoMembershipQuery:
        return _NoMembershipQuery()

    def execute(self, *args: object, **kwargs: object) -> _FakeResult:
        return _FakeResult()


# A generated job carries just the fields the public listing filter inspects.
@st.composite
def _jobs(draw: st.DrawFn) -> SimpleNamespace:
    now = datetime.now(timezone.utc)
    # Ages span both sides of the 90-day publication window.
    age_days = draw(st.integers(min_value=0, max_value=200))
    return SimpleNamespace(
        title=draw(st.text(max_size=20)),
        company=draw(st.text(max_size=20)),
        location=draw(st.text(max_size=20)),
        status=draw(st.sampled_from(_JOB_STATUSES)),
        country=draw(st.sampled_from(_MARKETS)),
        jobtype=draw(st.sampled_from(["Full Time", "Part Time", "Remote"])),
        remote=draw(st.booleans()),
        created_at=now - timedelta(days=age_days),
    )


def _is_publicly_visible(job: SimpleNamespace, market: dict, cutoff: datetime) -> bool:
    return job.status == "active" and job.country == market["country"] and job.created_at >= cutoff


@settings(max_examples=100)
@given(jobs=st.lists(_jobs(), max_size=12), market_country=st.sampled_from(_MARKETS))
def test_job_seeker_browses_without_membership(jobs: list[SimpleNamespace], market_country: str) -> None:
    """(a) Browsing published jobs succeeds for a viewer with no membership."""
    market = {"country": market_country}
    db = _FakeSession()

    # A job seeker: an authenticated user with no platform roles and no membership.
    seeker = SimpleNamespace(id=uuid4(), roles=[])
    company_id = uuid4()

    # No membership => no effective permissions at all, yet browsing must work:
    # browsing is not gated by any permission.
    assert effective_permissions(db, seeker, company_id) == frozenset()

    # _apply_filters takes NO viewer/membership argument: the visible set cannot
    # depend on the viewer's membership.
    result = _apply_filters(jobs, market, query=None, jobtype=None, remote=None)

    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    expected = [job for job in jobs if _is_publicly_visible(job, market, cutoff)]

    # Browsing returns exactly the publicly visible jobs (and only active ones).
    assert set(id(job) for job in result) == set(id(job) for job in expected)
    assert all(job.status == "active" for job in result)


@settings(max_examples=100)
@given(source=st.sampled_from(["platform", "import", "referral"]))
def test_job_seeker_applies_without_membership(source: str) -> None:
    """(b) Submitting an application succeeds for a job seeker with no membership."""
    db = _FakeSession()
    job_id = uuid4()
    # The job seeker is identified by their platform user id; no company / membership.
    candidate_user_id = uuid4()

    application = applications.create_application(
        db,
        job_id=job_id,
        candidate_user_id=candidate_user_id,
        source=source,
    )

    # The application is persisted at the first pipeline stage without any
    # membership being consulted (no company_id is involved).
    assert isinstance(application, Application)
    assert application in db.added
    assert db.flushed >= 1
    assert application.status == ApplicationStatus.applied
    assert application.candidate_user_id == candidate_user_id
    assert application.company_id is None
