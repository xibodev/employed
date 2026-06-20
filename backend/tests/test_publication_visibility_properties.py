"""Property-based test for public publication visibility (Property 24).

# Feature: multi-tenant-hiring-platform, Property 24: Blocked or unpublished
# publications are never publicly visible

The public job listing path restricts results to publications in a publicly
visible state. Concretely, both the SQL push-down (``_job_query_pushdown``) and
the DB-free Python fallback (``_apply_filters``) keep only rows whose
``status == "active"``. Moderation actions move a publication out of that
visible state: blocking sets ``status = "flagged"`` and unpublishing
(deactivation) sets ``status = "inactive"`` (see ``app/routers/verification.py``
and ``app/routers/jobs.py``). Therefore a public listing query must never
surface a blocked (``flagged``) or unpublished (``inactive``) publication,
regardless of how the surrounding set of jobs is composed.

This test exercises the real filter, ``app.routers.jobs._apply_filters``, with
generated ``SimpleNamespace`` stand-ins for jobs (each carrying a ``status``, a
``country`` matching the active market, and a recent ``created_at``). Driving the
production predicate directly keeps the property deterministic and DB-free while
still asserting the actual visibility contract.

Validates: Requirements 11.1, 11.2, 12.1
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

from hypothesis import given, settings
from hypothesis import strategies as st

from app.models.enums import JobStatus
from app.routers.jobs import _apply_filters
from app.services.market import MARKETS
from tests.conftest import utcnow

# The full set of statuses a publication can hold. "active" is the only publicly
# visible state; "flagged" (blocked) and "inactive" (unpublished) must never be
# returned, and "pending"/"filled" are likewise non-public.
_STATUSES = [member.value for member in JobStatus]

# Markets the platform serves; the active market supplies the "country" the
# public listing scopes to (shaped like get_current_market's return value).
_MARKETS = list(MARKETS.values())

# Statuses that represent a publication removed from public view by moderation.
_NEVER_VISIBLE = {JobStatus.flagged.value, JobStatus.inactive.value}


@st.composite
def jobs(draw: st.DrawFn, country: str) -> SimpleNamespace:
    """Generate a duck-typed job stand-in for the given market country.

    ``created_at`` is held within the 90-day freshness window and ``country``
    matches the active market so neither the recency nor the market predicate
    masks the status check under test. ``status`` is drawn across every possible
    JobStatus value so the generated set freely mixes active, blocked
    (``flagged``), unpublished (``inactive``), pending and filled publications.
    """
    days_old = draw(st.integers(min_value=0, max_value=89))
    return SimpleNamespace(
        status=draw(st.sampled_from(_STATUSES)),
        country=country,
        created_at=utcnow() - timedelta(days=days_old),
        title=draw(st.text(max_size=20)),
        company=draw(st.text(max_size=20)),
        location=draw(st.text(max_size=20)),
        jobtype="Full Time",
        remote=draw(st.booleans()),
    )


@settings(max_examples=100)
@given(data=st.data(), market=st.sampled_from(_MARKETS))
def test_blocked_or_unpublished_jobs_are_never_publicly_visible(data: st.DataObject, market: dict) -> None:
    """Property 24: a public listing returns only publicly visible jobs.

    For any set of jobs with assorted statuses, the public filter returns only
    publications in the publicly visible state (``active``) and never returns a
    blocked (``flagged``) or unpublished (``inactive``) publication.
    """
    items = data.draw(st.lists(jobs(country=market["country"]), max_size=12))

    visible = _apply_filters(items, market, query=None, jobtype=None, remote=None)

    # Every returned publication is in the single publicly visible state...
    assert all(job.status == JobStatus.active.value for job in visible)
    # ...and in particular none of them are blocked or unpublished.
    assert not any(job.status in _NEVER_VISIBLE for job in visible)
