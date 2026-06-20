from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, get_user_id
from app.database import get_db
from app.middleware.market import get_current_market
from app.models.company import Company
from app.models.enums import MarketKey
from app.schemas.companies import CompanyCreate, CompanyRead, DomainVerifyRequest
from app.services.companies import (
    create_company,
    verify_domain_via_dns,
    verify_domain_via_member_emails,
)
from app.services.rbac import COMPANY_VERIFY_DOMAIN, require_permission

router = APIRouter(prefix="/companies", tags=["companies"])


def _load_company(db: Session, company_id: UUID) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company


@router.post("", response_model=CompanyRead, status_code=status.HTTP_201_CREATED)
def create_company_endpoint(
    payload: CompanyCreate,
    db: Session = Depends(get_db),
    market: dict = Depends(get_current_market),
    current_user: Any = Depends(get_current_user),
) -> CompanyRead:
    """Create a Company; the authenticated user becomes its active org_owner (R1.1, R2.4).

    The market is taken from the per-request market context (resolved by
    subdomain), never from the client. The creating user's id is recorded as
    ``created_by`` and the company plus its owner membership are persisted
    atomically by the service; the request boundary owns the commit.
    """
    try:
        company = create_company(
            db,
            name=payload.name,
            market=MarketKey(market["key"]),
            created_by=get_user_id(current_user),
            description=payload.description,
            logo_url=payload.logo_url,
            website=payload.website,
        )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not create company",
        ) from exc

    db.refresh(company)
    return CompanyRead.model_validate(company)


@router.get("/{company_id}", response_model=CompanyRead)
def get_company_endpoint(
    company_id: UUID,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
) -> CompanyRead:
    """Read a single Company by id; 404 when it does not exist."""
    company = _load_company(db, company_id)
    return CompanyRead.model_validate(company)


@router.post("/{company_id}/verify-domain", response_model=CompanyRead)
def verify_company_domain_endpoint(
    company_id: UUID,
    payload: DomainVerifyRequest,
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission(COMPANY_VERIFY_DOMAIN)),
) -> CompanyRead:
    """Verify a Company domain via DNS TXT or matching member emails (R9.1/9.2).

    Guarded by the ``company:verify_domain`` permission, with the owning company
    resolved from the ``company_id`` path parameter. On success the domain is
    appended to ``verified_email_domains`` and the ``domain verified`` badge is
    attached (R9.3/9.5); a failed proof is mapped to ``422`` and changes nothing.
    """
    company = _load_company(db, company_id)

    method = payload.method or ("dns" if payload.expected_token else "member_email")
    if method == "dns":
        if not payload.expected_token:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="expected_token is required for DNS verification",
            )
        verified = verify_domain_via_dns(
            db,
            company=company,
            domain=payload.domain,
            expected_token=payload.expected_token,
        )
    else:
        verified = verify_domain_via_member_emails(db, company=company, domain=payload.domain)

    if not verified:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Domain verification failed",
        )

    db.commit()
    db.refresh(company)
    return CompanyRead.model_validate(company)
