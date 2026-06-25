from __future__ import annotations

import copy
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.enums import ProfileType
from app.models.profile import Profile
from app.models.profile_version import ProfileVersion

# JSON Resume top-level sections and their expected JSON types.
# Reference schema: https://jsonresume.org/schema
# Validation is intentionally lightweight (structural only): we confirm that the
# document is an object and that recognised sections carry the right JSON shape,
# without enforcing the full field-level schema (R13.5).
_ARRAY_SECTIONS: tuple[str, ...] = (
    "work",
    "volunteer",
    "education",
    "awards",
    "certificates",
    "publications",
    "skills",
    "languages",
    "interests",
    "references",
    "projects",
)
_OBJECT_SECTIONS: tuple[str, ...] = ("basics", "meta")

# Optional Profile columns that callers may seed when a live profile is first
# materialised. Required (NOT NULL) columns are handled explicitly below.
_OPTIONAL_PROFILE_FIELDS: tuple[str, ...] = (
    "user_name",
    "custom_image_url",
    "available_for_hire",
    "interested_in",
    "contact",
    "url",
    "resume_url",
    "github_url",
    "linkedin_url",
    "stackoverflow_url",
)


class JSONResumeValidationError(ValueError):
    """Raised when a document does not conform to the JSON Resume structure."""


def empty_json_resume() -> dict[str, Any]:
    """Return a minimal, valid JSON Resume working copy."""
    return {"basics": {}}


def validate_json_resume(document: Any) -> dict[str, Any]:
    """Validate the structural shape of a JSON Resume document (R13.5).

    Returns the document unchanged when valid; raises
    :class:`JSONResumeValidationError` otherwise. This is a lightweight check of
    the top-level structure, not a full JSON Schema validation.
    """
    if not isinstance(document, dict):
        raise JSONResumeValidationError("JSON Resume document must be a JSON object")

    for key in _OBJECT_SECTIONS:
        value = document.get(key)
        if value is not None and not isinstance(value, dict):
            raise JSONResumeValidationError(f"'{key}' section must be a JSON object")

    for key in _ARRAY_SECTIONS:
        value = document.get(key)
        if value is not None and not isinstance(value, list):
            raise JSONResumeValidationError(f"'{key}' section must be a JSON array")

    basics = document.get("basics")
    if isinstance(basics, dict):
        profiles = basics.get("profiles")
        if profiles is not None and not isinstance(profiles, list):
            raise JSONResumeValidationError("'basics.profiles' must be a JSON array")
        location = basics.get("location")
        if location is not None and not isinstance(location, dict):
            raise JSONResumeValidationError("'basics.location' must be a JSON object")

    return document


def get_live_profile(db: Session, user_id: UUID | str) -> Profile | None:
    """Return the single live working-copy Profile for *user_id*, if any (R13.1)."""
    return db.query(Profile).filter(Profile.user_id == user_id).one_or_none()


def ensure_live_profile(
    db: Session,
    *,
    user_id: UUID | str,
    defaults: dict[str, Any] | None = None,
    json_resume: dict[str, Any] | None = None,
) -> Profile:
    """Get the user's live Profile, creating it if absent (R13.1).

    The Platform maintains exactly one live Profile per user as the JSON Resume
    working copy. *defaults* seeds the required/optional columns when the profile
    is first created; an existing profile is returned untouched.
    """
    profile = get_live_profile(db, user_id)
    if profile is not None:
        return profile

    values = dict(defaults or {})
    resume = validate_json_resume(json_resume) if json_resume is not None else empty_json_resume()

    profile = Profile(
        user_id=user_id,
        name=values.get("name") or "",
        type=values.get("type") or ProfileType.individual,
        title=values.get("title") or "",
        location=values.get("location") or "",
        description=values.get("description") or "",
        json_resume=copy.deepcopy(resume),
    )
    for field in _OPTIONAL_PROFILE_FIELDS:
        if field in values and values[field] is not None:
            setattr(profile, field, values[field])

    db.add(profile)
    db.flush()
    return profile


def _next_version_number(db: Session, profile_id: UUID | str) -> int:
    """Return the next monotonic version number for *profile_id* (max + 1)."""
    current_max = (
        db.query(sa.func.max(ProfileVersion.version_number)).filter(ProfileVersion.profile_id == profile_id).scalar()
    )
    return int(current_max or 0) + 1


def save_version(
    db: Session,
    *,
    profile: Profile,
    json_resume: dict[str, Any] | None = None,
) -> ProfileVersion:
    """Write an immutable, append-only snapshot of the live profile (R13.2/13.3).

    When *json_resume* is supplied it is validated and becomes the live profile's
    working copy before the snapshot is taken. The resulting ``ProfileVersion``
    captures a deep copy of the live profile's JSON Resume at the moment of the
    save, assigned the next monotonic ``version_number`` for that profile.
    """
    if json_resume is not None:
        profile.json_resume = copy.deepcopy(validate_json_resume(json_resume))

    if profile.json_resume is None:
        profile.json_resume = empty_json_resume()
    validate_json_resume(profile.json_resume)

    # A freshly materialised profile needs its server-side id before a version
    # can reference it.
    if getattr(profile, "id", None) is None:
        db.add(profile)
        db.flush()

    snapshot = copy.deepcopy(dict(profile.json_resume))
    version = ProfileVersion(
        profile_id=profile.id,
        user_id=profile.user_id,
        version_number=_next_version_number(db, profile.id),
        json_resume=snapshot,
    )
    db.add(version)
    db.flush()
    return version
