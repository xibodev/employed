from __future__ import annotations

import os
import random
from datetime import timedelta
from typing import Any
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from slugify import slugify

from app.auth.dependencies import (
    get_current_user,
    get_optional_current_user,
    get_primary_email,
    get_user_id,
    is_admin_user,
    is_email_verified,
    load_user_by_id,
)
from app.config import settings
from app.database import get_db
from app.middleware.market import get_current_market
from app.schemas.jobs import JobCountResponse, JobCreate, JobListResponse, JobRead, JobUpdate
from app.services.email import send_job_status_changed_email, send_job_submitted_email
from app.services.html_sanitizer import sanitize_html
from app.services.model_utils import (
    delete,
    get_attr,
    get_by_id,
    query_all,
    query_by_user,
    query_count,
    resolve_model,
    save,
    set_attr,
    utcnow,
)
from app.services.rbac import JOB_POST, has_permission

router = APIRouter(prefix="/jobs", tags=["jobs"])

VALID_STATUSES = {"pending", "active", "flagged", "inactive", "filled"}
JOB_TYPES = {
    "Full Time",
    "Part Time",
    "Contract",
    "Temporary",
    "Internship",
    "Freelance",
    "Remote",
    "Volunteer",
    "Other",
}


def _job_model():
    return resolve_model("Job", "Jobs")


def _build_job_url(request: Request, job: Any) -> str:
    host = request.headers.get("host") or request.url.netloc
    scheme = request.url.scheme
    job_id = str(get_attr(job, "id", "_id", default=""))
    slug = get_attr(job, "slug", default=None) or slugify(get_attr(job, "title", default="job"))
    return f"{scheme}://{host}/jobs/{job_id}/{slug}"


def _poster_name(user: Any | None) -> str | None:
    if user is None:
        return None
    return get_attr(user, "display_name", "name", "full_name", "username", default=get_primary_email(user))


def _job_to_read(job: Any, request: Request, *, include_contact: bool = True) -> JobRead:
    return JobRead(
        id=str(get_attr(job, "id", "_id", default="")),
        slug=get_attr(job, "slug"),
        title=get_attr(job, "title", default=""),
        company=get_attr(job, "company"),
        country=get_attr(job, "country"),
        location=get_attr(job, "location"),
        url=get_attr(job, "url"),
        contact=get_attr(job, "contact") if include_contact else None,
        apply_whatsapp=get_attr(job, "apply_whatsapp", "applyWhatsApp"),
        jobtype=get_attr(job, "jobtype", "job_type"),
        description=get_attr(job, "description"),
        html_description=get_attr(job, "html_description", "htmlDescription"),
        remote=bool(get_attr(job, "remote", default=False)),
        salary_min=get_attr(job, "salary_min", "salaryMin"),
        salary_max=get_attr(job, "salary_max", "salaryMax"),
        salary_currency=get_attr(job, "salary_currency", "salaryCurrency"),
        salary_period=get_attr(job, "salary_period", "salaryPeriod"),
        user_id=(str(user_id) if (user_id := get_attr(job, "user_id", "userId")) is not None else None),
        user_name=get_attr(job, "user_name", "userName"),
        status=get_attr(job, "status"),
        featured_through=get_attr(job, "featured_through", "featuredThrough"),
        created_at=get_attr(job, "created_at", "createdAt"),
        updated_at=get_attr(job, "updated_at", "updatedAt"),
        published_at=get_attr(job, "published_at", "publishedAt"),
        site_url=_build_job_url(request, job),
    )


def _pushdown_list_jobs(db: Any, model: Any, market: dict) -> list[Any]:
    """Attempt database-level push-down of the most selective predicates.

    Falls back to the full table scan when the model fields cannot be
    resolved (e.g. in tests against a plain SQLite schema).
    """
    from app.services.model_utils import get_model_field

    status_field = get_model_field(model, "status")
    country_field = get_model_field(model, "country")
    created_field = get_model_field(model, "created_at", "createdAt")
    cutoff = utcnow() - timedelta(days=90)

    if status_field is not None and country_field is not None and created_field is not None:
        db_filters = [
            status_field == "active",
            country_field == market["country"],
            created_field >= cutoff,
        ]
        return query_all(db, model, filters=db_filters, order_by=created_field.desc())

    # TODO: push-down not available for this model — full scan (deprecation target)
    return query_all(db, model)


def _like_pattern(needle: str) -> str:
    escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _job_query_pushdown(
    model: Any,
    market: dict,
    query: str | None,
    jobtype: str | None,
    remote: bool | None,
    *,
    featured_after: Any | None = None,
):
    """Build the full SQL predicate set for /jobs list/count (EMP-010).

    Returns ``(filters, created_field)`` when every requested predicate can
    be pushed to the database, or ``None`` to signal the Python fallback
    (plain test rigs without ORM columns).
    """
    from sqlalchemy import func, or_

    from app.services.model_utils import get_model_field

    status_field = get_model_field(model, "status")
    country_field = get_model_field(model, "country")
    created_field = get_model_field(model, "created_at", "createdAt")
    if status_field is None or country_field is None or created_field is None:
        return None

    cutoff = utcnow() - timedelta(days=90)
    filters: list[Any] = [
        status_field == "active",
        country_field == market["country"],
        created_field >= cutoff,
    ]

    if query and query.strip():
        text_fields = [
            get_model_field(model, "title"),
            get_model_field(model, "company"),
            get_model_field(model, "location"),
        ]
        conditions = [
            func.lower(field).like(_like_pattern(query.strip().lower()), escape="\\")
            for field in text_fields
            if field is not None
        ]
        if not conditions:
            return None
        filters.append(or_(*conditions))

    if jobtype:
        jobtype_field = get_model_field(model, "jobtype", "job_type")
        if jobtype_field is None:
            return None
        filters.append(jobtype_field == jobtype)

    if remote is not None:
        remote_field = get_model_field(model, "remote")
        if remote_field is None:
            return None
        filters.append(remote_field == remote)

    if featured_after is not None:
        featured_field = get_model_field(model, "featured_through", "featuredThrough")
        if featured_field is None:
            return None
        filters.append(featured_field >= featured_after)

    return filters, created_field


def _apply_filters(
    items: list[Any], market: dict, query: str | None, jobtype: str | None, remote: bool | None
) -> list[Any]:
    cutoff = utcnow() - timedelta(days=90)
    filtered = []
    for item in items:
        created_at = get_attr(item, "created_at", "createdAt")
        status_value = get_attr(item, "status")
        country = get_attr(item, "country")
        if status_value != "active":
            continue
        if created_at and created_at < cutoff:
            continue
        if country and country != market["country"]:
            continue
        filtered.append(item)

    if query:
        lowered = query.strip().lower()
        filtered = [
            item
            for item in filtered
            if lowered in (get_attr(item, "title", default="") or "").lower()
            or lowered in (get_attr(item, "company", default="") or "").lower()
            or lowered in (get_attr(item, "location", default="") or "").lower()
        ]
    if jobtype:
        filtered = [item for item in filtered if get_attr(item, "jobtype", "job_type") == jobtype]
    if remote is not None:
        filtered = [item for item in filtered if bool(get_attr(item, "remote", default=False)) is remote]
    filtered.sort(key=lambda item: get_attr(item, "created_at", "createdAt", default=utcnow()), reverse=True)
    return filtered


def _assert_job_owner_or_admin(job: Any, user: Any) -> None:
    owner_id = get_attr(job, "user_id", "userId")
    if owner_id != get_user_id(user) and not is_admin_user(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only modify your own job")


# Action name contract shared with the frontend RecaptchaWidget (EMP-003).
RECAPTCHA_ACTION = "submit_job"


def _recaptcha_setting(*names: str, default: Any = None) -> Any:
    """Resolve a reCAPTCHA setting from pydantic Settings or the environment.

    EMP-002: the previous getattr(settings, 'RECAPTCHA_SECRET_KEY') lookups
    could never match the snake_case pydantic fields, so the secret was
    unreadable and anonymous job submission always failed. Mirrors the
    _setting helpers used by main.py and the webhook adapters.
    """
    for name in names:
        value = getattr(settings, name, getattr(settings, name.lower(), None))
        if value not in (None, ""):
            return value
        env_value = os.getenv(name)
        if env_value not in (None, ""):
            return env_value
    return default


def _recaptcha_bypass_enabled() -> bool:
    flag = _recaptcha_setting("RECAPTCHA_BYPASS_IN_DEVELOPMENT", default=False)
    enabled = str(flag).strip().lower() in {"1", "true", "yes", "on"}
    environment = str(getattr(settings, "environment", "development") or "development").strip().lower()
    return enabled and environment in {"development", "dev", "testing", "test"}


def _recaptcha_accepts(data: dict) -> bool:
    min_score = float(_recaptcha_setting("RECAPTCHA_MIN_SCORE", default=0.5))
    action = data.get("action")
    return bool(data.get("success")) and action in (None, RECAPTCHA_ACTION) and float(data.get("score", 0)) >= min_score


async def _verify_recaptcha(token: str | None, request: Request) -> bool:
    if _recaptcha_bypass_enabled():
        return True
    secret = _recaptcha_setting("RECAPTCHA_V3_SECRET_KEY", "RECAPTCHA_SECRET_KEY")
    if not secret or not token:
        return False
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data={
                "secret": secret,
                "response": token,
                "remoteip": request.client.host if request.client else None,
            },
        )
        response.raise_for_status()
        return _recaptcha_accepts(response.json())


def _payload_values(payload: Any, **kwargs) -> dict:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(**kwargs)
    return payload.dict(**kwargs)


def _coerce_company_id(value: Any) -> UUID | None:
    """Coerce a raw company identifier to a UUID, or ``None`` when absent.

    Raises ``400`` for a present-but-malformed identifier so a bad request is
    not silently treated as an anonymous post.
    """
    if value in (None, ""):
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid company identifier"
        ) from exc


def _authorize_company_post(db: Any, payload: JobCreate, user: Any | None) -> UUID | None:
    """Resolve the target company for an on-behalf-of post (R4.3/4.4/4.5).

    Returns the company id to stamp on the job when the caller is authorized,
    or ``None`` when no company was requested (legacy/anonymous job, R4.3).
    Rejects with ``403`` when the caller does not hold ``job:post`` in the
    target company via an active membership or a platform role (R4.5).
    """
    company_id = _coerce_company_id(getattr(payload, "company_id", None))
    if company_id is None:
        return None
    if user is None or not has_permission(db, user, JOB_POST, company_id=company_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to post on behalf of this company",
        )
    return company_id


def _set_job_fields(job: Any, payload: JobCreate | JobUpdate, market: dict, user: Any | None = None) -> None:
    values = _payload_values(payload, exclude_unset=True, exclude={"recaptcha_token", "company_id"})
    simple_fields = {
        "title": ("title",),
        "company": ("company",),
        "location": ("location",),
        "url": ("url",),
        "contact": ("contact",),
        "jobtype": ("jobtype", "job_type"),
        "remote": ("remote",),
    }
    for field, aliases in simple_fields.items():
        if field in values:
            set_attr(job, values[field], *aliases)
    if "apply_whatsapp" in values:
        set_attr(job, values["apply_whatsapp"], "apply_whatsapp", "applyWhatsApp")
    if "description" in values:
        set_attr(job, values["description"], "description")
        set_attr(job, sanitize_html(values["description"]), "html_description", "htmlDescription")
    for field, aliases in {
        "salary_min": ("salary_min", "salaryMin"),
        "salary_max": ("salary_max", "salaryMax"),
        "salary_currency": ("salary_currency", "salaryCurrency"),
        "salary_period": ("salary_period", "salaryPeriod"),
    }.items():
        if field in values:
            set_attr(job, values[field], *aliases)
    set_attr(job, market["country"], "country")
    set_attr(job, utcnow(), "updated_at", "updatedAt")
    if get_attr(job, "created_at", "createdAt") is None:
        set_attr(job, utcnow(), "created_at", "createdAt")
    if get_attr(job, "status") is None:
        set_attr(job, "pending", "status")
    if user is not None:
        set_attr(job, get_user_id(user), "user_id", "userId")
        set_attr(job, _poster_name(user), "user_name", "userName")


@router.get("", response_model=JobListResponse)
def list_jobs(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    query: str | None = None,
    jobtype: str | None = None,
    remote: bool | None = None,
    db: Any = Depends(get_db),
    market: dict = Depends(get_current_market),
    current_user: Any | None = Depends(get_optional_current_user),
):
    # EMP-028 policy: poster contact email is auth-gated everywhere.
    include_contact = current_user is not None
    model = _job_model()
    pushdown = _job_query_pushdown(model, market, query, jobtype, remote)
    if pushdown is not None:
        # EMP-010: search/type/remote predicates, COUNT(*), ORDER BY and
        # LIMIT/OFFSET all run in SQL instead of materializing the market.
        filters, created_field = pushdown
        if jobtype and jobtype not in JOB_TYPES:
            return JobListResponse(items=[], total=0, page=page, page_size=page_size)
        total = query_count(db, model, filters)
        items = query_all(
            db,
            model,
            filters=filters,
            order_by=created_field.desc(),
            limit=page_size,
            offset=(page - 1) * page_size,
        )
        return JobListResponse(
            items=[_job_to_read(item, request, include_contact=include_contact) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    # Fallback (test rigs without ORM columns): Python filtering
    candidates = _pushdown_list_jobs(db, model, market)
    items = _apply_filters(candidates, market, query, jobtype, remote)
    start = (page - 1) * page_size
    end = start + page_size
    return JobListResponse(
        items=[_job_to_read(item, request, include_contact=include_contact) for item in items[start:end]],
        total=len(items),
        page=page,
        page_size=page_size,
    )


@router.get("/featured", response_model=list[JobRead])
def list_featured_jobs(
    request: Request,
    db: Any = Depends(get_db),
    market: dict = Depends(get_current_market),
    current_user: Any | None = Depends(get_optional_current_user),
):
    now = utcnow()
    model = _job_model()
    pushdown = _job_query_pushdown(model, market, None, None, None, featured_after=now)
    if pushdown is not None:
        filters, created_field = pushdown
        candidates = query_all(db, model, filters=filters, order_by=created_field.desc())
    else:
        candidates = [
            item
            for item in _pushdown_list_jobs(db, model, market)
            if get_attr(item, "featured_through", "featuredThrough")
            and get_attr(item, "featured_through", "featuredThrough") >= now
        ]
    sample_size = min(3, len(candidates))
    chosen = random.sample(candidates, sample_size) if sample_size else []
    # EMP-028 policy: poster contact email is auth-gated everywhere.
    return [_job_to_read(item, request, include_contact=current_user is not None) for item in chosen]


@router.get("/count", response_model=JobCountResponse)
def count_jobs(
    query: str | None = None,
    jobtype: str | None = None,
    remote: bool | None = None,
    db: Any = Depends(get_db),
    market: dict = Depends(get_current_market),
):
    model = _job_model()
    pushdown = _job_query_pushdown(model, market, query, jobtype, remote)
    if pushdown is not None:
        if jobtype and jobtype not in JOB_TYPES:
            return JobCountResponse(total=0)
        filters, _ = pushdown
        return JobCountResponse(total=query_count(db, model, filters))
    candidates = _pushdown_list_jobs(db, model, market)
    items = _apply_filters(candidates, market, query, jobtype, remote)
    return JobCountResponse(total=len(items))


@router.get("/mine", response_model=list[JobRead])
def list_my_jobs(
    request: Request,
    db: Any = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    user_id = get_user_id(current_user)
    items = query_by_user(db, _job_model(), user_id)
    return [_job_to_read(item, request) for item in items]


@router.get("/{job_id}", response_model=JobRead)
def get_job(
    job_id: str,
    request: Request,
    db: Any = Depends(get_db),
    market: dict = Depends(get_current_market),
    current_user: Any | None = Depends(get_optional_current_user),
):
    job = get_by_id(db, _job_model(), job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    country = get_attr(job, "country")
    status_value = get_attr(job, "status")
    if country and country != market["country"] and not (current_user and is_admin_user(current_user)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if status_value != "active":
        # EMP-008: pre-moderation/inactive listings (including poster contact
        # details) must only be visible to the owner or an admin — not to any
        # authenticated account.
        is_owner = current_user is not None and get_attr(job, "user_id", "userId") == get_user_id(current_user)
        if not (is_owner or (current_user is not None and is_admin_user(current_user))):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    # EMP-028 policy: the poster's contact email is auth-gated — anonymous
    # payloads (and therefore the SSR'd HTML source) omit it; the frontend
    # offers an explicit signed-in reveal instead.
    return _job_to_read(job, request, include_contact=current_user is not None)


@router.post("", response_model=JobRead, status_code=status.HTTP_201_CREATED)
async def create_job(
    payload: JobCreate,
    request: Request,
    db: Any = Depends(get_db),
    market: dict = Depends(get_current_market),
    current_user: Any | None = Depends(get_optional_current_user),
):
    if payload.jobtype not in JOB_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid job type")
    if current_user is not None and not is_email_verified(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email verification required")
    if current_user is None and not await _verify_recaptcha(payload.recaptcha_token, request):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="reCAPTCHA validation failed")

    company_id = _authorize_company_post(db, payload, current_user)

    job = _job_model()()
    _set_job_fields(job, payload, market, current_user)
    if company_id is not None:
        set_attr(job, company_id, "company_id")
    saved = save(db, job)
    if current_user is not None:
        email = get_primary_email(current_user)
        if email:
            send_job_submitted_email(email, get_attr(saved, "title", default="Job"), _build_job_url(request, saved))
    return _job_to_read(saved, request)


@router.put("/{job_id}", response_model=JobRead)
def update_job(
    job_id: str,
    payload: JobUpdate,
    request: Request,
    db: Any = Depends(get_db),
    market: dict = Depends(get_current_market),
    current_user: Any = Depends(get_current_user),
):
    if not is_email_verified(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email verification required")
    job = get_by_id(db, _job_model(), job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    _assert_job_owner_or_admin(job, current_user)
    previous_status = get_attr(job, "status")
    _set_job_fields(job, payload, market, current_user)
    if previous_status == "active" and not is_admin_user(current_user):
        # EMP-008: owner edits of an approved listing must go back through
        # moderation; otherwise content can be swapped post-approval,
        # bypassing the admin gate.
        history = list(get_attr(job, "status_history", "statusHistory", default=[]) or [])
        history.append(
            {
                "at": utcnow().isoformat(),
                "by": str(get_user_id(current_user) or ""),
                "from": "active",
                "to": "pending",
                "reason": "owner edit requires re-moderation",
            }
        )
        set_attr(job, history[-100:], "status_history", "statusHistory")
        set_attr(job, "pending", "status")
    return _job_to_read(save(db, job), request)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(
    job_id: str,
    db: Any = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    job = get_by_id(db, _job_model(), job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    _assert_job_owner_or_admin(job, current_user)
    delete(db, job)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{job_id}/deactivate", response_model=JobRead)
def deactivate_job(
    job_id: str,
    request: Request,
    filled: bool = False,
    db: Any = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    job = get_by_id(db, _job_model(), job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    _assert_job_owner_or_admin(job, current_user)
    if get_attr(job, "status") != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only active jobs can be deactivated")
    new_status = "filled" if filled else "inactive"
    set_attr(job, new_status, "status")
    set_attr(job, utcnow(), "updated_at", "updatedAt")
    saved = save(db, job)
    # EMP-016: notify the JOB OWNER when someone else (an admin) deactivates
    # their listing. Previously the email went to the acting admin instead.
    owner_id = get_attr(saved, "user_id", "userId")
    actor_id = get_user_id(current_user)
    if owner_id is not None and owner_id != actor_id:
        owner = load_user_by_id(db, owner_id)
        owner_email = get_primary_email(owner) if owner is not None else None
        if owner_email:
            send_job_status_changed_email(
                owner_email, get_attr(saved, "title", default="Job"), new_status, _build_job_url(request, saved)
            )
    return _job_to_read(saved, request)
