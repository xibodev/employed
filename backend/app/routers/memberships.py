from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, get_user_id
from app.database import get_db
from app.models.company import Company
from app.models.membership import Membership
from app.schemas.memberships import MembershipInviteRequest, MembershipRead
from app.services.memberships import (
    MembershipError,
    accept_invitation,
    invite_member,
    suspend_member,
)
from app.services.rbac import COMPANY_MANAGE_MEMBERS, require_permission

router = APIRouter(prefix="/companies/{company_id}/members", tags=["memberships"])


def _load_company(db: Session, company_id: UUID) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company


def _load_membership(db: Session, company_id: UUID, membership_id: UUID) -> Membership:
    membership = db.get(Membership, membership_id)
    if membership is None or membership.company_id != company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found")
    return membership


@router.get("", response_model=list[MembershipRead])
def list_members_endpoint(
    company_id: UUID,
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission(COMPANY_MANAGE_MEMBERS)),
) -> list[MembershipRead]:
    """List a Company's memberships (R2.6/2.9).

    Guarded by the ``company:manage_members`` permission with the owning company
    resolved from the ``company_id`` path parameter.
    """
    _load_company(db, company_id)
    memberships = (
        db.query(Membership)
        .filter(Membership.company_id == company_id)
        .order_by(Membership.created_at)
        .all()
    )
    return [MembershipRead.model_validate(m) for m in memberships]


@router.post("", response_model=MembershipRead, status_code=status.HTTP_201_CREATED)
def invite_member_endpoint(
    company_id: UUID,
    payload: MembershipInviteRequest,
    db: Session = Depends(get_db),
    current_user: Any = Depends(require_permission(COMPANY_MANAGE_MEMBERS)),
) -> MembershipRead:
    """Invite a user to a Company, creating an ``invited`` membership (R2.6).

    Guarded by the ``company:manage_members`` permission with the owning company
    resolved from the ``company_id`` path parameter. The inviting user is taken
    from the authenticated request and recorded as ``invited_by``; the request
    boundary owns the commit.
    """
    _load_company(db, company_id)
    try:
        membership = invite_member(
            db,
            company_id=company_id,
            user_id=payload.user_id,
            role=payload.role,
            invited_by=get_user_id(current_user),
        )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not invite member",
        ) from exc

    db.refresh(membership)
    return MembershipRead.model_validate(membership)


@router.post("/{membership_id}/accept", response_model=MembershipRead)
def accept_invitation_endpoint(
    company_id: UUID,
    membership_id: UUID,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
) -> MembershipRead:
    """Accept an invitation, moving an ``invited`` membership to ``active`` (R2.7/2.8).

    Accessible only to the invited user: the authenticated user may accept their
    own membership only. Accepting a non-``invited`` membership is rejected with
    ``409`` and leaves the status unchanged (R2.8). The request boundary owns the
    commit.
    """
    membership = _load_membership(db, company_id, membership_id)
    if str(membership.user_id) != str(get_user_id(current_user)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to perform this action",
        )

    try:
        accept_invitation(db, membership=membership)
        db.commit()
    except MembershipError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Invitation cannot be accepted",
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not accept invitation",
        ) from exc

    db.refresh(membership)
    return MembershipRead.model_validate(membership)


@router.post("/{membership_id}/suspend", response_model=MembershipRead)
def suspend_member_endpoint(
    company_id: UUID,
    membership_id: UUID,
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission(COMPANY_MANAGE_MEMBERS)),
) -> MembershipRead:
    """Suspend a membership, setting its status to ``suspended`` (R2.9).

    Guarded by the ``company:manage_members`` permission with the owning company
    resolved from the ``company_id`` path parameter. The request boundary owns
    the commit.
    """
    membership = _load_membership(db, company_id, membership_id)
    try:
        suspend_member(db, membership=membership)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not suspend member",
        ) from exc

    db.refresh(membership)
    return MembershipRead.model_validate(membership)
