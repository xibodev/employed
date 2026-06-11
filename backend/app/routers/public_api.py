from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from app.database import get_db
from app.middleware.market import get_current_market
from app.middleware.rate_limit import rate_limit
from app.routers.jobs import JOB_TYPES, _apply_filters, _job_model, _job_query_pushdown, _job_to_read
from app.schemas.jobs import JobListResponse, JobRead
from app.services.model_utils import get_attr, query_all, query_count, utcnow

router = APIRouter(prefix="/api", tags=["public-api"])


@router.get("/jobs", response_model=JobListResponse, dependencies=[Depends(rate_limit(60, 60, "public_api_jobs"))])
def public_jobs(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    query: str | None = None,
    jobtype: str | None = None,
    remote: bool | None = None,
    db: Any = Depends(get_db),
    market: dict = Depends(get_current_market),
):
    model = _job_model()
    pushdown = _job_query_pushdown(model, market, query, jobtype, remote)
    if pushdown is not None:
        # CARTO-001: same SQL-side predicates, COUNT(*), ORDER BY and
        # LIMIT/OFFSET as /jobs (EMP-010) — these aliases are what the
        # frontend actually calls, so they must not materialize the market.
        if jobtype and jobtype not in JOB_TYPES:
            return JobListResponse(items=[], total=0, page=page, page_size=page_size)
        filters, created_field = pushdown
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
            items=[_job_to_read(item, request, include_contact=False) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    # Fallback (test rigs without ORM columns): Python filtering
    items = _apply_filters(query_all(db, model), market, query, jobtype, remote)
    start = (page - 1) * page_size
    end = start + page_size
    return JobListResponse(
        items=[_job_to_read(item, request, include_contact=False) for item in items[start:end]],
        total=len(items),
        page=page,
        page_size=page_size,
    )


@router.get(
    "/featuredJobs",
    response_model=list[JobRead],
    dependencies=[Depends(rate_limit(60, 60, "public_api_featured_jobs"))],
)
def public_featured_jobs(
    request: Request,
    db: Any = Depends(get_db),
    market: dict = Depends(get_current_market),
):
    now = utcnow()
    model = _job_model()
    pushdown = _job_query_pushdown(model, market, None, None, None, featured_after=now)
    if pushdown is not None:
        # CARTO-001: featured predicate + ORDER BY + LIMIT 3 in SQL. Unlike
        # /jobs/featured (random sample), this alias keeps its historical
        # deterministic newest-first contract.
        filters, created_field = pushdown
        items = query_all(db, model, filters=filters, order_by=created_field.desc(), limit=3)
        return [_job_to_read(item, request, include_contact=False) for item in items]

    # Fallback (test rigs without ORM columns): Python filtering
    items = [
        item
        for item in _apply_filters(query_all(db, model), market, None, None, None)
        if get_attr(item, "featured_through", "featuredThrough")
        and get_attr(item, "featured_through", "featuredThrough") >= now
    ]
    items = items[:3]
    return [_job_to_read(item, request, include_contact=False) for item in items]
