from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.models.webhook import WebhookEndpoint
from app.schemas.webhooks import WebhookEndpointCreate, WebhookEndpointRead
from app.services.rbac import COMPANY_MANAGE, has_permission, require_permission
from app.services.webhooks import register_endpoint

router = APIRouter(prefix="/webhook-endpoints", tags=["webhooks"])


def _load_endpoint(db: Session, endpoint_id: UUID) -> WebhookEndpoint:
    endpoint = db.get(WebhookEndpoint, endpoint_id)
    if endpoint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook endpoint not found")
    return endpoint


@router.post("", response_model=WebhookEndpointRead, status_code=status.HTTP_201_CREATED)
def register_endpoint_route(
    payload: WebhookEndpointCreate,
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission(COMPANY_MANAGE)),
) -> WebhookEndpointRead:
    """Register an outbound webhook endpoint (R20.4).

    Guarded by the ``company:manage`` permission, with the owning company
    resolved from the ``company_id`` field in the request body. A platform-level
    endpoint (``company_id`` omitted) is therefore only registrable by a holder
    of the permission across all tenants (e.g. a platform super admin). The
    service flushes the endpoint within this transaction; the request boundary
    owns the commit. The signing secret is never returned in the response.
    """
    try:
        endpoint = register_endpoint(
            db,
            company_id=payload.company_id,
            url=payload.url,
            secret=payload.secret,
            events=payload.events,
            active=payload.active,
        )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not register webhook endpoint",
        ) from exc

    db.refresh(endpoint)
    return WebhookEndpointRead.model_validate(endpoint)


@router.get("", response_model=list[WebhookEndpointRead])
def list_endpoints_route(
    db: Session = Depends(get_db),
    company_id: UUID | None = Query(default=None),
    _: Any = Depends(require_permission(COMPANY_MANAGE)),
) -> list[WebhookEndpointRead]:
    """List registered webhook endpoints (R20.4).

    Guarded by ``company:manage`` against the ``company_id`` query parameter:
    scoping the listing to a company authorizes that company's org managers,
    while an unscoped listing requires the platform-level permission. When
    ``company_id`` is provided the result is filtered to that company.
    """
    stmt = select(WebhookEndpoint)
    if company_id is not None:
        stmt = stmt.where(WebhookEndpoint.company_id == company_id)
    endpoints = db.execute(stmt).scalars().all()
    return [WebhookEndpointRead.model_validate(endpoint) for endpoint in endpoints]


@router.delete("/{endpoint_id}", response_model=WebhookEndpointRead)
def deactivate_endpoint_route(
    endpoint_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WebhookEndpointRead:
    """Deactivate a registered webhook endpoint (R20.4).

    Authorization is resolved against the endpoint's owning company so an org
    manager can deactivate their own company's endpoint while a platform-level
    endpoint requires the permission across all tenants. Deactivation is a soft
    delete (``active = False``) so emission stops fanning out to the endpoint
    without losing its delivery history.
    """
    endpoint = _load_endpoint(db, endpoint_id)
    if not has_permission(db, current_user, COMPANY_MANAGE, endpoint.company_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to perform this action",
        )

    endpoint.active = False
    db.commit()
    db.refresh(endpoint)
    return WebhookEndpointRead.model_validate(endpoint)
