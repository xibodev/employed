"""Property-based test for JobPosting JSON-LD mapping (Property 23).

The Platform emits job data at integration boundaries as schema.org
``JobPosting`` JSON-LD via :func:`app.services.export.to_job_posting_jsonld`
(R18.2, R18.3). This module verifies that, for any job, the emitted document is
a valid ``JobPosting`` envelope (``@context``/``@type``) and faithfully preserves
the job's core fields: title, description, location, and posting date.

``to_job_posting_jsonld`` is a pure, side-effect-free mapper that reads attributes
off whatever entity it is handed, so generated jobs are lightweight duck-typed
stand-ins (``SimpleNamespace``) rather than persisted ORM rows. This keeps the
test focused on the mapping contract across a wide spread of field values.

Validates: Requirements 18.2, 18.3
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.models.enums import Country, JobType, SalaryCurrency, SalaryPeriod
from app.services.export import to_job_posting_jsonld

# Text without surrogate code points keeps generated values JSON-friendly and
# avoids encoding artifacts unrelated to the mapping under test.
_safe_text = st.text(
    alphabet=st.characters(min_codepoint=1, blacklist_categories=("Cs",)),
    max_size=40,
)

# Datetimes are timezone-aware to mirror the timezone(True) columns on Job, and
# bounded to a sane range so .isoformat() stays well-defined.
_datetimes = st.datetimes(
    min_value=datetime(2000, 1, 1),
    max_value=datetime(2100, 1, 1),
).map(lambda dt: dt.replace(tzinfo=timezone.utc))


@st.composite
def jobs(draw: st.DrawFn) -> SimpleNamespace:
    """Generate a lightweight, duck-typed stand-in for a ``Job``.

    Core fields (title/description/location/posting date) are always present so
    the preservation assertions have something to compare against. ``title`` and
    ``description`` are non-nullable on the real model, so they are required here
    too. Optional fields are independently included/omitted to spread coverage
    over the mapper's conditional branches.
    """

    title = draw(_safe_text.filter(lambda s: s.strip() != ""))
    description = draw(_safe_text.filter(lambda s: s.strip() != ""))
    location = draw(_safe_text.filter(lambda s: s.strip() != ""))

    # description maps from html_description when present, else description.
    html_description = draw(st.none() | _safe_text.filter(lambda s: s.strip() != ""))

    # datePosted comes from published_at, falling back to created_at. created_at
    # is always present; published_at is sometimes None to exercise the fallback.
    created_at = draw(_datetimes)
    published_at = draw(st.none() | _datetimes)

    return SimpleNamespace(
        id=uuid4(),
        title=title,
        description=description,
        html_description=html_description,
        location=location,
        created_at=created_at,
        published_at=published_at,
        expired_at=draw(st.none() | _datetimes),
        job_type=draw(st.none() | st.sampled_from(list(JobType))),
        country=draw(st.none() | st.sampled_from(list(Country))),
        company=draw(st.none() | _safe_text),
        url=draw(st.none() | _safe_text),
        remote=draw(st.booleans()),
        salary_min=draw(st.none() | st.integers(min_value=0, max_value=10**9)),
        salary_max=draw(st.none() | st.integers(min_value=0, max_value=10**9)),
        salary_currency=draw(st.none() | st.sampled_from(list(SalaryCurrency))),
        salary_period=draw(st.none() | st.sampled_from(list(SalaryPeriod))),
    )


# Feature: multi-tenant-hiring-platform, Property 23: Jobs map to valid schema.org JobPosting JSON-LD
@settings(max_examples=100, deadline=None)
@given(job=jobs())
def test_jobs_map_to_valid_job_posting_jsonld(job: SimpleNamespace) -> None:
    """For any job, the emitted JSON-LD is a valid JobPosting envelope and
    preserves the job's core fields (title, description, location, posting date).

    Validates: Requirements 18.2, 18.3
    """

    document = to_job_posting_jsonld(job)

    # Valid schema.org JobPosting envelope (R18.2).
    assert document["@context"] == "https://schema.org"
    assert document["@type"] == "JobPosting"

    # Core field preservation (R18.3): title and description.
    assert document["title"] == job.title
    expected_description = job.html_description or job.description
    assert document["description"] == expected_description

    # Posting date: published_at when present, else created_at, rendered ISO 8601.
    expected_posted = job.published_at or job.created_at
    assert document["datePosted"] == expected_posted.isoformat()

    # Location is preserved inside the schema.org Place/PostalAddress.
    job_location = document["jobLocation"]
    assert job_location["@type"] == "Place"
    assert job_location["address"]["addressLocality"] == job.location


if __name__ == "__main__":  # pragma: no cover - convenience for ad-hoc runs
    pytest.main([__file__, "-v"])
