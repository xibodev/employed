from __future__ import annotations

from enum import Enum
from typing import Type

import sqlalchemy as sa


class JobStatus(str, Enum):
    pending = "pending"
    active = "active"
    flagged = "flagged"
    inactive = "inactive"
    filled = "filled"


class JobType(str, Enum):
    full_time = "Full Time"
    part_time = "Part Time"
    contract = "Contract"
    temporary = "Temporary"
    internship = "Internship"
    freelance = "Freelance"
    remote = "Remote"
    volunteer = "Volunteer"
    other = "Other"


class Country(str, Enum):
    mexico = "Mexico"
    mozambique = "Mozambique"


class MarketKey(str, Enum):
    mx = "mx"
    mz = "mz"


class SalaryCurrency(str, Enum):
    mxn = "MXN"
    mzn = "MZN"
    usd = "USD"


class SalaryPeriod(str, Enum):
    hour = "hour"
    day = "day"
    week = "week"
    month = "month"
    year = "year"


class ProfileType(str, Enum):
    individual = "Individual"
    company = "Company"


class ProfileStatus(str, Enum):
    pending = "pending"
    active = "active"
    flagged = "flagged"


class PaymentProviderKey(str, Enum):
    stripe = "stripe"
    mpesa = "mpesa"
    emola = "emola"


class PaymentStatus(str, Enum):
    pending = "pending"
    awaiting_user = "awaiting_user"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    expired = "expired"


class ReportReason(str, Enum):
    spam = "spam"
    scam = "scam"
    discriminatory = "discriminatory"
    wrong_country = "wrong_country"
    expired_or_filled = "expired_or_filled"
    duplicate = "duplicate"


class ReportResolution(str, Enum):
    pending = "pending"
    reviewed = "reviewed"
    dismissed = "dismissed"
    job_removed = "job_removed"


class OAuthProvider(str, Enum):
    google = "google"
    facebook = "facebook"
    github = "github"
    twitter = "twitter"


class VerificationState(str, Enum):
    unverified = "unverified"
    pending = "pending"
    verified = "verified"
    rejected = "rejected"
    revoked = "revoked"
    flagged = "flagged"


class PlatformRole(str, Enum):
    platform_super_admin = "platform_super_admin"
    platform_moderator = "platform_moderator"
    platform_support = "platform_support"


class TenantRole(str, Enum):
    org_owner = "org_owner"
    org_admin = "org_admin"
    recruiter = "recruiter"
    member = "member"  # viewer


class MembershipStatus(str, Enum):
    invited = "invited"
    active = "active"
    suspended = "suspended"


class ApplicationStatus(str, Enum):
    applied = "applied"
    reviewed = "reviewed"
    shortlisted = "shortlisted"
    rejected = "rejected"
    hired = "hired"


class WebhookEvent(str, Enum):
    job_published = "job.published"
    application_created = "application.created"
    application_status_changed = "application.status_changed"


EnumType = Type[Enum]


def enum_values(enum_cls: EnumType) -> list[str]:
    return [member.value for member in enum_cls]


def pg_enum(enum_cls: EnumType, name: str) -> sa.Enum:
    return sa.Enum(
        enum_cls,
        name=name,
        values_callable=enum_values,
        native_enum=True,
        validate_strings=True,
    )
