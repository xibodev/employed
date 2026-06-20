from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.application import Application
from app.models.company import Company
from app.schemas.applications import ApplicationRead, ApplicationStatusChangeRequest
from app.services.applications import change_status
from app.services.rbac import (
    APPLICATION_ADVANCE,
    APPLICATION_REVIEW,
    has_permission,
    require_permission,
)

router = APIRouter(tags=["applications"])


def _load_company(db: Session, company_id: UUID) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company


def _load_application(db: Session, application_id: UUID) -> Application:
    application = db.get(Application, application_id)
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    return application


@router.get("/companies/{company_id}/applications", response_model=list[ApplicationRead])
def list_applications_endpoint(
    company_id: UUID,
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission(APPLICATION_REVIEW)),
) -> list[ApplicationRead]:
    """List the Applications for a Company (R17.1).

    Guarded by the ``application:review`` permission with the owning company
    resolved from the ``company_id`` path parameter; a user without that
    permission in the company is rejected with ``403`` (R17.6).
    """
    _load_company(db, company_id)
    applications = (
        db.query(Application)
        .filter(Application.company_id == company_id)
        .order_by(Application.created_at)
        .all()
    )
    return [ApplicationRead.model_validate(a) for a in applications]


@router.patch("/applications/{application_id}/status", response_model=ApplicationRead)
def change_application_status_endpoint(
    application_id: UUID,
    payload: ApplicationStatusChangeRequest,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
) -> ApplicationRead:
    """Advance an Application to a new pipeline stage (R17.3/17.4/17.5/17.6).

    The owning company is resolved from the Application itself and the action is
    guarded by the ``application:advance`` permission in that company; a user
    without it is rejected with ``403`` (R17.6). On success the new stage is
    persisted (R17.3), an audit entry is written (R17.5), and the
    ``application.status_changed`` event is emitted (R17.4). The request boundary
    owns the commit.
    """
    application = _load_application(db, application_id)

    if not has_permission(db, current_user, APPLICATION_ADVANCE, application.company_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to perform this action",
        )

    try:
        change_status(
            db,
            application=application,
            new_status=payload.new_status,
            actor=current_user,
        )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not change application status",
        ) from exc

    db.refresh(application)
    return ApplicationRead.model_validate(application)
