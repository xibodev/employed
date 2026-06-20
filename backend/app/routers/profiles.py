from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import get_current_user, get_user_id, is_admin_user
from app.database import get_db
from app.models.profile_version import ProfileVersion
from app.schemas.profiles import (
    ProfileCreate,
    ProfileRead,
    ProfileUpdate,
    ProfileVersionRead,
    ProfileVersionSaveRequest,
    ProfileVersionSummary,
)
from app.services.html_sanitizer import sanitize_html
from app.services.model_utils import get_attr, query_all, resolve_model, save, set_attr, utcnow
from app.services.profiles_versioning import (
    JSONResumeValidationError,
    ensure_live_profile,
    save_version,
)

router = APIRouter(prefix="/profiles", tags=["profiles"])


def _profile_model():
    return resolve_model("Profile", "Profiles")


def _profile_to_read(profile: Any) -> ProfileRead:
    return ProfileRead(
        id=str(get_attr(profile, "id", "_id", default="")),
        user_id=(str(user_id) if (user_id := get_attr(profile, "user_id", "userId")) is not None else None),
        user_name=get_attr(profile, "user_name", "userName"),
        name=get_attr(profile, "name"),
        type=get_attr(profile, "type"),
        title=get_attr(profile, "title"),
        location=get_attr(profile, "location"),
        description=get_attr(profile, "description"),
        html_description=get_attr(profile, "html_description", "htmlDescription"),
        available_for_hire=bool(get_attr(profile, "available_for_hire", "availableForHire", default=False)),
        interested_in=list(get_attr(profile, "interested_in", "interestedIn", default=[]) or []),
        contact=get_attr(profile, "contact"),
        url=get_attr(profile, "url"),
        resume_url=get_attr(profile, "resume_url", "resumeUrl"),
        github_url=get_attr(profile, "github_url", "githubUrl"),
        linkedin_url=get_attr(profile, "linkedin_url", "linkedinUrl"),
        stackoverflow_url=get_attr(profile, "stackoverflow_url", "stackoverflowUrl"),
        custom_image_url=get_attr(profile, "custom_image_url", "customImageUrl"),
        status=get_attr(profile, "status"),
        created_at=get_attr(profile, "created_at", "createdAt"),
        updated_at=get_attr(profile, "updated_at", "updatedAt"),
    )


def _find_profile_by_user(db: Any, user_id: str):
    for profile in query_all(db, _profile_model()):
        if get_attr(profile, "user_id", "userId") == user_id:
            return profile
    return None


def _payload_values(payload: Any, **kwargs) -> dict:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(**kwargs)
    return payload.dict(**kwargs)


def _apply_profile_fields(profile: Any, payload: ProfileCreate | ProfileUpdate, user: Any) -> None:
    values = _payload_values(payload, exclude_unset=True)
    for field in ("name", "type", "title", "location", "contact", "url"):
        if field in values:
            set_attr(profile, values[field], field)
    if "description" in values:
        set_attr(profile, values["description"], "description")
        set_attr(profile, sanitize_html(values["description"]), "html_description", "htmlDescription")
    for field, aliases in {
        "available_for_hire": ("available_for_hire", "availableForHire"),
        "interested_in": ("interested_in", "interestedIn"),
        "resume_url": ("resume_url", "resumeUrl"),
        "github_url": ("github_url", "githubUrl"),
        "linkedin_url": ("linkedin_url", "linkedinUrl"),
        "stackoverflow_url": ("stackoverflow_url", "stackoverflowUrl"),
        "custom_image_url": ("custom_image_url", "customImageUrl"),
    }.items():
        if field in values:
            set_attr(profile, values[field], *aliases)
    set_attr(profile, get_user_id(user), "user_id", "userId")
    set_attr(
        profile,
        get_attr(user, "display_name", "name", "full_name", "username", default=get_attr(user, "email")),
        "user_name",
        "userName",
    )
    set_attr(profile, utcnow(), "updated_at", "updatedAt")
    if get_attr(profile, "created_at", "createdAt") is None:
        set_attr(profile, utcnow(), "created_at", "createdAt")
    if get_attr(profile, "status") is None:
        set_attr(profile, "pending", "status")


@router.post(
    "/versions",
    response_model=ProfileVersionSummary,
    status_code=status.HTTP_201_CREATED,
)
def save_profile_version(
    payload: ProfileVersionSaveRequest,
    db: Any = Depends(get_db),
    current_user: Any = Depends(get_current_user),
) -> ProfileVersionSummary:
    """Save an immutable snapshot of the authenticated owner's live profile (R13.2).

    An optional ``json_resume`` body updates the live working copy before the
    snapshot is taken. The live profile is materialised on first save (R13.1).
    """
    user_id = get_user_id(current_user)
    try:
        profile = ensure_live_profile(db, user_id=user_id)
        version = save_version(db, profile=profile, json_resume=payload.json_resume)
    except JSONResumeValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    db.commit()
    db.refresh(version)
    return ProfileVersionSummary.model_validate(version)


@router.get("/versions", response_model=list[ProfileVersionSummary])
def list_profile_versions(
    db: Any = Depends(get_db),
    current_user: Any = Depends(get_current_user),
) -> list[ProfileVersionSummary]:
    """List the authenticated owner's profile versions, oldest first (R13.2/13.3)."""
    user_id = get_user_id(current_user)
    versions = (
        db.query(ProfileVersion)
        .filter(ProfileVersion.user_id == user_id)
        .order_by(ProfileVersion.version_number.asc())
        .all()
    )
    return [ProfileVersionSummary.model_validate(version) for version in versions]


@router.get("/versions/{version_id}", response_model=ProfileVersionRead)
def get_profile_version(
    version_id: UUID,
    db: Any = Depends(get_db),
    current_user: Any = Depends(get_current_user),
) -> ProfileVersionRead:
    """Return a single immutable profile version owned by the authenticated user."""
    user_id = get_user_id(current_user)
    version = db.get(ProfileVersion, version_id)
    if version is None or version.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile version not found")
    return ProfileVersionRead.model_validate(version)


@router.get("/{user_id}", response_model=ProfileRead)
def get_profile(user_id: str, db: Any = Depends(get_db)):
    profile = _find_profile_by_user(db, user_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    if get_attr(profile, "status") != "active":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return _profile_to_read(profile)


@router.post("", response_model=ProfileRead, status_code=status.HTTP_201_CREATED)
def upsert_profile(payload: ProfileCreate, db: Any = Depends(get_db), current_user: Any = Depends(get_current_user)):
    profile = _find_profile_by_user(db, get_user_id(current_user)) or _profile_model()()
    _apply_profile_fields(profile, payload, current_user)
    return _profile_to_read(save(db, profile))


@router.put("", response_model=ProfileRead)
def update_profile(payload: ProfileUpdate, db: Any = Depends(get_db), current_user: Any = Depends(get_current_user)):
    profile = _find_profile_by_user(db, get_user_id(current_user))
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    owner_id = get_attr(profile, "user_id", "userId")
    if owner_id != get_user_id(current_user) and not is_admin_user(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only update your own profile")
    _apply_profile_fields(profile, payload, current_user)
    return _profile_to_read(save(db, profile))
