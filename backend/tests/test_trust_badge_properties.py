"""Property-based tests for trust-badge derivation and reconciliation.

# Feature: multi-tenant-hiring-platform, Property 8: Trust badges equal the derived condition set

Trust is a *set of named badges* derived from concrete underlying conditions
(DD-5, R8): a badge is attached while its condition holds and removed once it
ceases to hold. The pure :func:`app.services.trust.derive_badges` reports the set
that *should* be attached for an entity's current condition state, and
:func:`app.services.trust.reconcile_badges` makes the persisted
``Company.trust_badges`` list equal that set -- attaching newly satisfied badges
and dropping ones whose condition no longer holds.

``derive_badges`` is a pure function that inspects only the entity's own
attributes (``verification_status``, ``verified_email_domains`` and explicit
boolean flags in ``external_refs``), so the production
:class:`~app.models.company.Company` / :class:`~app.models.job.Job` /
:class:`~app.models.profile.Profile` instances can be constructed in memory and
fed varied condition states directly -- no database is required. Only ``Company``
persists a ``trust_badges`` column, so ``reconcile_badges`` is exercised against a
``Company`` stand-in with a lightweight fake session that records ``flush`` calls.
"""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.models.company import Company
from app.models.enums import VerificationState
from app.models.job import Job
from app.models.profile import Profile
from app.services.trust import (
    COMPANY_BADGES,
    JOB_BADGES,
    PROFILE_BADGES,
    derive_badges,
    reconcile_badges,
)


class _FakeSession:
    """Minimal stand-in for a SQLAlchemy ``Session`` capturing ``flush`` calls.

    ``reconcile_badges`` mutates the entity's ``trust_badges`` list in place and
    then flushes within the caller's transaction (DD-10). Reconciliation needs no
    real persistence to be observable, so this records only that a flush occurred.
    """

    def __init__(self) -> None:
        self.flushed = 0

    def flush(self) -> None:
        self.flushed += 1


# Printable-ASCII keeps generated domain/value text clear of surrogate/encoding
# edge cases unrelated to the property under test.
_text = st.text(alphabet=st.characters(min_codepoint=33, max_codepoint=126), min_size=1, max_size=16)
_states = st.sampled_from(list(VerificationState))


def _refs_with(flags: dict[str, bool], noise: dict[str, Any]) -> dict[str, Any]:
    """Build an ``external_refs`` map from boolean condition flags plus noise.

    Only the truthy flags are written, mirroring how the owning services set
    explicit boolean conditions. ``noise`` carries unrelated keys (other external
    identifiers) that must never themselves produce a badge.
    """
    refs: dict[str, Any] = dict(noise)
    for key, value in flags.items():
        refs[key] = value
    return refs


# external_refs noise: keys that are NOT recognised badge conditions. They must
# never contribute a badge regardless of value.
_noise = st.dictionaries(
    st.sampled_from(["stripe", "greenhouse", "lever", "ats_id", "crm"]),
    st.none() | st.booleans() | st.integers() | _text,
    max_size=3,
)


# --- Company -----------------------------------------------------------------

_company_state = st.fixed_dictionaries(
    {
        "verification_status": _states,
        "verified_email_domains": st.lists(_text, max_size=4),
        "email_verified": st.booleans(),
        "payment_verified": st.booleans(),
        "activity": st.booleans(),
        "noise": _noise,
    }
)


def _build_company(state: dict[str, Any]) -> Company:
    refs = _refs_with(
        {
            "email_verified": state["email_verified"],
            "payment_verified": state["payment_verified"],
            "activity": state["activity"],
        },
        state["noise"],
    )
    return Company(
        name="Acme",
        slug="acme",
        verification_status=state["verification_status"],
        verified_email_domains=list(state["verified_email_domains"]),
        external_refs=refs,
        trust_badges=[],
    )


def _expected_company_badges(state: dict[str, Any]) -> set[str]:
    """The badge set the company's conditions semantically imply (R8.2/9.3/10.2)."""
    expected: set[str] = set()
    if state["email_verified"]:
        expected.add("email verified")
    if state["verified_email_domains"]:
        expected.add("domain verified")
    if state["verification_status"] == VerificationState.verified:
        expected.add("business-document verified")
    if state["payment_verified"]:
        expected.add("payment verified")
    if state["activity"]:
        expected.add("activity")
    return expected


# Feature: multi-tenant-hiring-platform, Property 8: Trust badges equal the derived condition set
@settings(max_examples=100, deadline=None)
@given(state=_company_state)
def test_company_derive_badges_equals_condition_set(state: dict[str, Any]) -> None:
    """For any Company condition state, ``derive_badges`` equals exactly the set
    of badges whose underlying conditions currently hold.

    Validates: Requirements 8.5, 8.6, 9.3, 10.2
    """
    company = _build_company(state)
    derived = derive_badges(company)

    assert derived == _expected_company_badges(state)
    # Derivation never invents a badge outside the company catalog.
    assert derived <= COMPANY_BADGES


# Feature: multi-tenant-hiring-platform, Property 8: Trust badges equal the derived condition set
@settings(max_examples=100, deadline=None)
@given(
    state=_company_state,
    initial=st.lists(
        st.sampled_from(sorted(COMPANY_BADGES) + ["stale-badge", "legacy"]),
        max_size=7,
    ),
)
def test_reconcile_makes_company_badges_equal_derivation(
    state: dict[str, Any], initial: list[str]
) -> None:
    """After reconciliation the Company's ``trust_badges`` equals ``derive_badges``.

    Starting from an arbitrary pre-existing badge list (which may include badges
    whose condition no longer holds, and unknown/legacy badges), reconciliation
    attaches every satisfied badge and removes every unsatisfied one, leaving the
    persisted list set-equal to the derived set with no duplicates. This covers
    both attachment (R8.5) and removal when a condition ceases (R8.6).

    Validates: Requirements 8.5, 8.6, 9.3, 10.2
    """
    company = _build_company(state)
    # Seed the entity with arbitrary prior badges (dedupe preserving order, as a
    # persisted MutableList would not carry duplicates).
    seen: set[str] = set()
    company.trust_badges = [b for b in initial if not (b in seen or seen.add(b))]

    derived = derive_badges(company)
    db = _FakeSession()
    reconcile_badges(db, company)

    # The attached set equals the derived condition set exactly...
    assert set(company.trust_badges) == derived
    # ...with no duplicate entries left behind...
    assert len(company.trust_badges) == len(set(company.trust_badges))
    # ...and the change was flushed within the caller's transaction.
    assert db.flushed == 1


# Feature: multi-tenant-hiring-platform, Property 8: Trust badges equal the derived condition set
@settings(max_examples=100, deadline=None)
@given(state=_company_state, second=_company_state)
def test_reconcile_tracks_conditions_changing_over_time(
    state: dict[str, Any], second: dict[str, Any]
) -> None:
    """Reconciliation tracks a Company whose conditions change between calls.

    A first reconciliation attaches the badges for the initial state; mutating the
    company's conditions and reconciling again makes the badge list equal the new
    derived set -- badges appear as conditions become satisfied and disappear as
    they cease.

    Validates: Requirements 8.5, 8.6, 9.3, 10.2
    """
    company = _build_company(state)
    db = _FakeSession()

    reconcile_badges(db, company)
    assert set(company.trust_badges) == _expected_company_badges(state)

    # Conditions change: rewrite the company's condition-bearing attributes.
    company.verification_status = second["verification_status"]
    company.verified_email_domains = list(second["verified_email_domains"])
    company.external_refs = _refs_with(
        {
            "email_verified": second["email_verified"],
            "payment_verified": second["payment_verified"],
            "activity": second["activity"],
        },
        second["noise"],
    )

    reconcile_badges(db, company)
    assert set(company.trust_badges) == _expected_company_badges(second)
    assert len(company.trust_badges) == len(set(company.trust_badges))


# --- Job ---------------------------------------------------------------------

_job_state = st.fixed_dictionaries(
    {
        "salary_min": st.none() | st.integers(min_value=0, max_value=1_000_000),
        "salary_max": st.none() | st.integers(min_value=0, max_value=1_000_000),
        "company_verified": st.booleans(),
        "responsive": st.booleans(),
        "noise": _noise,
    }
)


def _expected_job_badges(state: dict[str, Any]) -> set[str]:
    expected: set[str] = set()
    if state["company_verified"]:
        expected.add("posted by verified company")
    if state["salary_min"] is not None or state["salary_max"] is not None:
        expected.add("salary disclosed")
    if state["responsive"]:
        expected.add("responsive")
    return expected


# Feature: multi-tenant-hiring-platform, Property 8: Trust badges equal the derived condition set
@settings(max_examples=100, deadline=None)
@given(state=_job_state)
def test_job_derive_badges_equals_condition_set(state: dict[str, Any]) -> None:
    """For any Job condition state, ``derive_badges`` equals the satisfied set.

    Validates: Requirements 8.5, 8.6, 9.3, 10.2
    """
    job = Job(
        title="Engineer",
        contact="jobs@example.com",
        description="desc",
        salary_min=state["salary_min"],
        salary_max=state["salary_max"],
        external_refs=_refs_with(
            {"company_verified": state["company_verified"], "responsive": state["responsive"]},
            state["noise"],
        ),
    )
    derived = derive_badges(job)

    assert derived == _expected_job_badges(state)
    assert derived <= JOB_BADGES


# --- Profile -----------------------------------------------------------------

_profile_state = st.fixed_dictionaries(
    {
        "verification_status": _states,
        "email_verified": st.booleans(),
        "phone_verified": st.booleans(),
        "noise": _noise,
    }
)


def _expected_profile_badges(state: dict[str, Any]) -> set[str]:
    expected: set[str] = set()
    if state["email_verified"]:
        expected.add("email verified")
    if state["verification_status"] == VerificationState.verified:
        expected.add("identity verified")
    if state["phone_verified"]:
        expected.add("phone verified")
    return expected


# Feature: multi-tenant-hiring-platform, Property 8: Trust badges equal the derived condition set
@settings(max_examples=100, deadline=None)
@given(state=_profile_state)
def test_profile_derive_badges_equals_condition_set(state: dict[str, Any]) -> None:
    """For any Profile condition state, ``derive_badges`` equals the satisfied set.

    Validates: Requirements 8.5, 8.6, 9.3, 10.2
    """
    profile = Profile(
        user_id=None,
        name="Jane",
        title="Engineer",
        location="Maputo",
        description="about",
        verification_status=state["verification_status"],
        external_refs=_refs_with(
            {"email_verified": state["email_verified"], "phone_verified": state["phone_verified"]},
            state["noise"],
        ),
    )
    derived = derive_badges(profile)

    assert derived == _expected_profile_badges(state)
    assert derived <= PROFILE_BADGES


if __name__ == "__main__":  # pragma: no cover - convenience for ad-hoc runs
    pytest.main([__file__, "-v"])
