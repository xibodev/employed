"""Composable trust badges (DD-5, R8).

Trust is modelled as a *set of named badges*, never a single numeric score
(R8.1). Each badge corresponds to a concrete underlying condition; a badge is
attached while its condition holds and removed once it ceases to hold
(R8.5/8.6).

The module exposes two functions:

* :func:`derive_badges` — a **pure** function that, given an entity, returns the
  set of badge names that *should* be attached for that entity's current
  condition state. It inspects only the entity's own attributes and performs no
  I/O, so it is trivially testable across generated inputs (Property 8).
* :func:`reconcile_badges` — applies the derived set to a persisted entity,
  attaching newly satisfied badges and removing ones whose condition no longer
  holds, then flushes within the caller's transaction (DD-10: synchronous
  ``Session``; we flush, never commit).

Condition sources follow the schema: column-backed conditions read their column
(``verified_email_domains``, ``salary_min``/``salary_max``, ``verification_status``);
conditions without a dedicated column read an explicit boolean flag from the
entity's ``external_refs`` JSONB map (DD-8 — the documented extensibility point),
which the owning services set as those conditions change.

Only :class:`~app.models.company.Company` persists a ``trust_badges`` column;
Job and Profile badges are derived for display. :func:`reconcile_badges` is
therefore a no-op for entities that do not carry a ``trust_badges`` attribute,
so it can be called uniformly (e.g. from the verification state machine) for any
verifiable entity.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.enums import VerificationState
from app.models.job import Job
from app.models.profile import Profile

# Badge name catalogs (R8.2/8.3/8.4). Names are the canonical, human-readable
# identifiers used throughout the platform and stored verbatim in ``trust_badges``.
COMPANY_BADGES: frozenset[str] = frozenset(
    {
        "email verified",
        "domain verified",
        "business-document verified",
        "payment verified",
        "activity",
    }
)
JOB_BADGES: frozenset[str] = frozenset(
    {
        "posted by verified company",
        "salary disclosed",
        "responsive",
    }
)
PROFILE_BADGES: frozenset[str] = frozenset(
    {
        "email verified",
        "identity verified",
        "phone verified",
    }
)


def _refs(entity: Any) -> dict[str, Any]:
    """Return the entity's ``external_refs`` map, tolerating an unset value.

    A freshly constructed instance may not yet have the column default applied,
    so fall back to an empty mapping rather than assuming ``{}`` is present.
    """
    return entity.external_refs or {}


def _company_badges(company: Company) -> set[str]:
    """Badges whose condition currently holds for a Company (R8.2)."""
    refs = _refs(company)
    badges: set[str] = set()
    # email verified: the company's contact/owner email has been confirmed.
    if refs.get("email_verified"):
        badges.add("email verified")
    # domain verified: at least one domain has been proven (R9.3/9.5 append to
    # verified_email_domains on success).
    if company.verified_email_domains:
        badges.add("domain verified")
    # business-document verified: the higher manual tier, reached when the
    # verification state machine marks the company verified (R10.2, R11.5).
    if company.verification_status == VerificationState.verified:
        badges.add("business-document verified")
    # payment verified: a successful payment has been recorded for the company.
    if refs.get("payment_verified"):
        badges.add("payment verified")
    # activity: the company is actively engaged (e.g. recent live postings).
    if refs.get("activity"):
        badges.add("activity")
    return badges


def _job_badges(job: Job) -> set[str]:
    """Badges whose condition currently holds for a Job (R8.3)."""
    refs = _refs(job)
    badges: set[str] = set()
    # posted by verified company: set by the job/company services when the
    # posting company is verified.
    if refs.get("company_verified"):
        badges.add("posted by verified company")
    # salary disclosed: a salary figure (lower and/or upper bound) is present.
    if job.salary_min is not None or job.salary_max is not None:
        badges.add("salary disclosed")
    # responsive: the poster responds to applications in a timely manner.
    if refs.get("responsive"):
        badges.add("responsive")
    return badges


def _profile_badges(profile: Profile) -> set[str]:
    """Badges whose condition currently holds for a Profile (R8.4)."""
    refs = _refs(profile)
    badges: set[str] = set()
    # email verified: the profile owner's email has been confirmed.
    if refs.get("email_verified"):
        badges.add("email verified")
    # identity verified: reached when the verification state machine marks the
    # profile verified (R11.6).
    if profile.verification_status == VerificationState.verified:
        badges.add("identity verified")
    # phone verified: the profile owner's phone number has been confirmed.
    if refs.get("phone_verified"):
        badges.add("phone verified")
    return badges


def derive_badges(entity: Any) -> frozenset[str]:
    """Compute the set of badges that *should* be attached to ``entity``.

    Pure function (no I/O): inspects only the entity's current condition state
    and dispatches on its type. Unknown entity types yield an empty set rather
    than raising, so the function is safe to call defensively.
    """
    if isinstance(entity, Company):
        return frozenset(_company_badges(entity))
    if isinstance(entity, Job):
        return frozenset(_job_badges(entity))
    if isinstance(entity, Profile):
        return frozenset(_profile_badges(entity))
    return frozenset()


def reconcile_badges(db: Session, entity: Any) -> None:
    """Make ``entity.trust_badges`` equal :func:`derive_badges` (R8.5/8.6).

    Attaches every badge whose condition now holds and removes every badge whose
    condition no longer holds, mutating the ``MutableList`` in place so the JSONB
    change is tracked and persisted. The work happens in the caller's
    transaction — we flush, never commit (DD-10).

    Entities without a persisted ``trust_badges`` column (Job, Profile — whose
    badges are derived for display) are a no-op, so this can be called uniformly
    for any verifiable entity.
    """
    if not hasattr(entity, "trust_badges"):
        return

    derived = derive_badges(entity)
    current: list[str] = entity.trust_badges

    # Remove badges whose condition no longer holds (R8.6).
    for badge in list(current):
        if badge not in derived:
            current.remove(badge)
    # Attach badges whose condition now holds (R8.5); deterministic order.
    for badge in sorted(derived):
        if badge not in current:
            current.append(badge)

    db.flush()
