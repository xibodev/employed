"""Pure mappers that render platform entities into standard interchange schemas (R18).

These functions are deliberately side-effect free: they read attributes off ORM
instances (or duck-typed stand-ins) and return plain ``dict`` documents. They never
touch the database, so they are safe to call from routers, workers, and tests alike.

- :func:`to_json_resume` — candidate data as a JSON Resume document (R18.1).
- :func:`to_job_posting_jsonld` — job data as schema.org ``JobPosting`` JSON-LD (R18.2).
- :func:`to_normalized_application` — application data as a normalized object (R18.3).

The ``Base.id`` UUID is used as the stable public identifier for each entity (R18.4).
"""

from __future__ import annotations

import copy
from datetime import datetime
from enum import Enum
from typing import Any

# schema.org JobPosting employmentType vocabulary keyed by our JobType value.
# https://schema.org/JobPosting → employmentType
_EMPLOYMENT_TYPE_BY_JOB_TYPE: dict[str, str] = {
    "Full Time": "FULL_TIME",
    "Part Time": "PART_TIME",
    "Contract": "CONTRACTOR",
    "Temporary": "TEMPORARY",
    "Internship": "INTERN",
    "Freelance": "CONTRACTOR",
    "Remote": "OTHER",
    "Volunteer": "VOLUNTEER",
    "Other": "OTHER",
}

# ISO 3166-1 alpha-2 codes for the markets we operate in, used to populate the
# JobPosting jobLocation PostalAddress addressCountry field.
_COUNTRY_CODE: dict[str, str] = {
    "Mexico": "MX",
    "Mozambique": "MZ",
}

# schema.org QuantitativeValue unitText keyed by our SalaryPeriod value.
_SALARY_UNIT_TEXT: dict[str, str] = {
    "hour": "HOUR",
    "day": "DAY",
    "week": "WEEK",
    "month": "MONTH",
    "year": "YEAR",
}


def _enum_value(value: Any) -> Any:
    """Return the primitive value of an Enum, leaving plain values untouched."""
    return value.value if isinstance(value, Enum) else value


def _iso(value: Any) -> str | None:
    """Render a datetime as an ISO 8601 string; pass through other truthy values."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _stable_id(entity: Any) -> str | None:
    """Stable public identifier for an entity (R18.4): its ``id`` as a string."""
    identifier = getattr(entity, "id", None)
    return str(identifier) if identifier is not None else None


def to_json_resume(profile_or_version: Any) -> dict[str, Any]:
    """Return the candidate's JSON Resume document (R18.1).

    Accepts either a live ``Profile`` or an immutable ``ProfileVersion``; both
    carry the canonical resume in their ``json_resume`` column. When a stored
    document exists it is returned verbatim (a deep copy, so callers cannot mutate
    ORM state) which keeps storage→export lossless (Property 13). When it is
    absent or empty, a minimal document is synthesized from the profile's
    structured columns so the boundary always speaks JSON Resume.
    """
    stored = getattr(profile_or_version, "json_resume", None)
    if stored:
        return copy.deepcopy(dict(stored))

    basics: dict[str, Any] = {}
    name = getattr(profile_or_version, "name", None)
    if name is not None:
        basics["name"] = name
    title = getattr(profile_or_version, "title", None)
    if title is not None:
        basics["label"] = title
    description = getattr(profile_or_version, "description", None)
    if description is not None:
        basics["summary"] = description
    url = getattr(profile_or_version, "url", None)
    if url is not None:
        basics["url"] = url
    location = getattr(profile_or_version, "location", None)
    if location is not None:
        basics["location"] = {"address": location}

    profiles: list[dict[str, str]] = []
    for network, attr in (
        ("GitHub", "github_url"),
        ("LinkedIn", "linkedin_url"),
        ("Stack Overflow", "stackoverflow_url"),
    ):
        link = getattr(profile_or_version, attr, None)
        if link:
            profiles.append({"network": network, "url": link})
    if profiles:
        basics["profiles"] = profiles

    return {"basics": basics}


def to_job_posting_jsonld(job: Any) -> dict[str, Any]:
    """Render a job as schema.org ``JobPosting`` JSON-LD (R18.2, R18.3).

    The document always carries ``@context``/``@type`` and preserves the job's
    core fields — title, description, location, and posting date (Property 23).
    """
    posted_at = getattr(job, "published_at", None) or getattr(job, "created_at", None)

    document: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "identifier": _stable_id(job),
        "title": getattr(job, "title", None),
        "description": getattr(job, "html_description", None) or getattr(job, "description", None),
        "datePosted": _iso(posted_at),
    }

    valid_through = _iso(getattr(job, "expired_at", None))
    if valid_through is not None:
        document["validThrough"] = valid_through

    job_type = _enum_value(getattr(job, "job_type", None))
    if job_type is not None:
        document["employmentType"] = _EMPLOYMENT_TYPE_BY_JOB_TYPE.get(job_type, "OTHER")

    company = getattr(job, "company", None)
    if company:
        document["hiringOrganization"] = {"@type": "Organization", "name": company}

    document["jobLocation"] = _job_location(job)

    if getattr(job, "remote", False):
        document["jobLocationType"] = "TELECOMMUTE"

    base_salary = _base_salary(job)
    if base_salary is not None:
        document["baseSalary"] = base_salary

    url = getattr(job, "url", None)
    if url:
        document["url"] = url

    return document


def _job_location(job: Any) -> dict[str, Any]:
    """Build the schema.org ``Place`` jobLocation for a job."""
    address: dict[str, Any] = {"@type": "PostalAddress"}
    location = getattr(job, "location", None)
    if location is not None:
        address["addressLocality"] = location
    country = _enum_value(getattr(job, "country", None))
    if country is not None:
        address["addressCountry"] = _COUNTRY_CODE.get(country, country)
    return {"@type": "Place", "address": address}


def _base_salary(job: Any) -> dict[str, Any] | None:
    """Build the schema.org ``MonetaryAmount`` baseSalary, or ``None`` when absent."""
    salary_min = getattr(job, "salary_min", None)
    salary_max = getattr(job, "salary_max", None)
    if salary_min is None and salary_max is None:
        return None

    value: dict[str, Any] = {"@type": "QuantitativeValue"}
    if salary_min is not None:
        value["minValue"] = salary_min
    if salary_max is not None:
        value["maxValue"] = salary_max
    period = _enum_value(getattr(job, "salary_period", None))
    if period is not None:
        value["unitText"] = _SALARY_UNIT_TEXT.get(period, period)

    monetary: dict[str, Any] = {"@type": "MonetaryAmount", "value": value}
    currency = _enum_value(getattr(job, "salary_currency", None))
    if currency is not None:
        monetary["currency"] = currency
    return monetary


def to_normalized_application(application: Any) -> dict[str, Any]:
    """Render an application as a normalized Application object (R18.3).

    Carries the stable identifier (R18.4) and the canonical application fields,
    referencing the candidate either by platform user id or by inline snapshot.
    """
    candidate: dict[str, Any] = {}
    candidate_user_id = getattr(application, "candidate_user_id", None)
    if candidate_user_id is not None:
        candidate["userId"] = str(candidate_user_id)
    candidate_snapshot = getattr(application, "candidate_snapshot", None)
    if candidate_snapshot:
        candidate["snapshot"] = copy.deepcopy(dict(candidate_snapshot))

    company_id = getattr(application, "company_id", None)
    resume_version_id = getattr(application, "resume_version_id", None)
    external_refs = getattr(application, "external_refs", None)

    return {
        "id": _stable_id(application),
        "jobId": str(application.job_id) if getattr(application, "job_id", None) is not None else None,
        "companyId": str(company_id) if company_id is not None else None,
        "candidate": candidate,
        "status": _enum_value(getattr(application, "status", None)),
        "resumeVersionId": str(resume_version_id) if resume_version_id is not None else None,
        "coverNote": getattr(application, "cover_note", None),
        "source": getattr(application, "source", None),
        "externalRefs": dict(external_refs) if external_refs else {},
        "createdAt": _iso(getattr(application, "created_at", None)),
        "updatedAt": _iso(getattr(application, "updated_at", None)),
    }
