"""RBAC and multi-tenancy schema.

Adds tenancy (companies, memberships), profile versioning, applications,
audit logging, and webhook delivery infrastructure. Also extends jobs,
profiles, and users with verification state and external references.

Revision ID: 003_rbac_and_tenancy
Revises: 002_add_password_changed_at
Create Date: 2026-05-24 01:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "003_rbac_and_tenancy"
down_revision = "002_add_password_changed_at"
branch_labels = None
depends_on = None

# New native enum types. ``create_type=False`` is a PostgreSQL-dialect flag
# (hence ``postgresql.ENUM``, not the generic ``sa.Enum`` — the generic type
# silently ignores it and would re-emit ``CREATE TYPE`` per table). The types
# are created/dropped explicitly in ``upgrade``/``downgrade`` so that the
# ``create_table``/``add_column`` calls that reference them never attempt an
# implicit ``CREATE TYPE`` (which fails once a second table reuses the type).
verification_state_enum = postgresql.ENUM(
    "unverified",
    "pending",
    "verified",
    "rejected",
    "revoked",
    "flagged",
    name="verificationstate",
    create_type=False,
)
platform_role_enum = postgresql.ENUM(
    "platform_super_admin",
    "platform_moderator",
    "platform_support",
    name="platformrole",
    create_type=False,
)
tenant_role_enum = postgresql.ENUM(
    "org_owner",
    "org_admin",
    "recruiter",
    "member",
    name="tenantrole",
    create_type=False,
)
membership_status_enum = postgresql.ENUM(
    "invited",
    "active",
    "suspended",
    name="membershipstatus",
    create_type=False,
)
application_status_enum = postgresql.ENUM(
    "applied",
    "reviewed",
    "shortlisted",
    "rejected",
    "hired",
    name="applicationstatus",
    create_type=False,
)
webhook_event_enum = postgresql.ENUM(
    "job.published",
    "application.created",
    "application.status_changed",
    name="webhookevent",
    create_type=False,
)

# Existing enum reused by the companies table (already created in revision 001).
market_key_enum = postgresql.ENUM("mx", "mz", name="market_key_enum", create_type=False)

_NEW_ENUMS = (
    verification_state_enum,
    platform_role_enum,
    tenant_role_enum,
    membership_status_enum,
    application_status_enum,
    webhook_event_enum,
)


def upgrade() -> None:
    bind = op.get_bind()
    for enum in _NEW_ENUMS:
        enum.create(bind, checkfirst=True)

    op.create_table(
        "companies",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("slug", sa.String(length=256), nullable=False),
        sa.Column("market", market_key_enum, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("logo_url", sa.String(length=2048), nullable=True),
        sa.Column("website", sa.String(length=2048), nullable=True),
        sa.Column(
            "verification_status",
            verification_state_enum,
            nullable=False,
            server_default=sa.text("'unverified'"),
        ),
        sa.Column(
            "created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "verified_email_domains",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "trust_badges",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "external_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("market", "slug", name="uq_companies_market_slug"),
    )

    op.create_table(
        "memberships",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", tenant_role_enum, nullable=False),
        sa.Column("status", membership_status_enum, nullable=False),
        sa.Column(
            "invited_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "company_id", name="uq_memberships_user_company"),
    )

    op.create_table(
        "profile_versions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("json_resume", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("profile_id", "version_number", name="uq_profile_versions_profile_version"),
    )

    op.create_table(
        "applications",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "candidate_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("candidate_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", application_status_enum, nullable=False, server_default=sa.text("'applied'")),
        sa.Column(
            "resume_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profile_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("cover_note", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False, server_default=sa.text("'platform'")),
        sa.Column(
            "external_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "candidate_user_id IS NOT NULL OR candidate_snapshot IS NOT NULL",
            name="ck_applications_candidate_present",
        ),
    )

    op.create_table(
        "audit_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("actor_label", sa.String(length=128), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "webhook_endpoints",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("secret", sa.String(length=256), nullable=False),
        sa.Column(
            "events",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "webhook_deliveries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "endpoint_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("webhook_endpoints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event", webhook_event_enum, nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # Extend jobs.
    op.add_column(
        "jobs",
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "verification_status",
            verification_state_enum,
            nullable=False,
            server_default=sa.text("'unverified'"),
        ),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "external_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index("ix_jobs_company_id", "jobs", ["company_id"], unique=False)

    # Extend profiles.
    op.add_column("profiles", sa.Column("json_resume", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column(
        "profiles",
        sa.Column(
            "verification_status",
            verification_state_enum,
            nullable=False,
            server_default=sa.text("'unverified'"),
        ),
    )
    op.add_column(
        "profiles",
        sa.Column(
            "external_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    # Extend users.
    op.add_column(
        "users",
        sa.Column(
            "external_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "external_refs")

    op.drop_column("profiles", "external_refs")
    op.drop_column("profiles", "verification_status")
    op.drop_column("profiles", "json_resume")

    op.drop_index("ix_jobs_company_id", table_name="jobs")
    op.drop_column("jobs", "external_refs")
    op.drop_column("jobs", "verification_status")
    op.drop_column("jobs", "company_id")

    op.drop_table("webhook_deliveries")
    op.drop_table("webhook_endpoints")
    op.drop_table("audit_logs")
    op.drop_table("applications")
    op.drop_table("profile_versions")
    op.drop_table("memberships")
    op.drop_table("companies")

    bind = op.get_bind()
    for enum in reversed(_NEW_ENUMS):
        enum.drop(bind, checkfirst=True)
