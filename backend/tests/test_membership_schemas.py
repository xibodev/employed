"""Unit tests for the membership request/response schemas (task 7.3).

These are example tests (not property-based) that exercise the new
``MembershipInviteRequest`` / ``MembershipRead`` Pydantic models without a live
database. They lock down the invite request shape (R2.6) and the read view
returned by the invite/accept/suspend/list endpoints.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.enums import MembershipStatus, TenantRole
from app.schemas.memberships import MembershipInviteRequest, MembershipRead


def test_invite_request_defaults_role_to_member() -> None:
    user_id = uuid4()
    request = MembershipInviteRequest(user_id=user_id)
    assert request.user_id == user_id
    assert request.role is TenantRole.member


def test_invite_request_coerces_role_from_value() -> None:
    request = MembershipInviteRequest(user_id=uuid4(), role="recruiter")
    assert request.role is TenantRole.recruiter


def test_invite_request_requires_user_id() -> None:
    with pytest.raises(ValidationError):
        MembershipInviteRequest(role=TenantRole.org_admin)


def test_invite_request_rejects_unknown_role() -> None:
    with pytest.raises(ValidationError):
        MembershipInviteRequest(user_id=uuid4(), role="emperor")


def test_membership_read_from_attributes_roundtrip() -> None:
    membership = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        company_id=uuid4(),
        role=TenantRole.org_admin,
        status=MembershipStatus.invited,
        invited_by=uuid4(),
    )
    read = MembershipRead.model_validate(membership)
    assert read.id == membership.id
    assert read.user_id == membership.user_id
    assert read.company_id == membership.company_id
    assert read.role is TenantRole.org_admin
    assert read.status is MembershipStatus.invited
    assert read.invited_by == membership.invited_by


def test_membership_read_allows_null_invited_by() -> None:
    read = MembershipRead.model_validate(
        SimpleNamespace(
            id=uuid4(),
            user_id=uuid4(),
            company_id=uuid4(),
            role=TenantRole.member,
            status=MembershipStatus.active,
            invited_by=None,
        )
    )
    assert read.invited_by is None
