"""Smoke tests for shared schema invariants on the core tenancy models.

These are example/introspection tests (not property-based): they assert the
shape of the SQLAlchemy table metadata without requiring a live database.

Covered invariants:
- `external_refs` is a JSONB dict column on Company, Job, Profile, User and
  Application (Requirement 1.2 / 19.1 — extensible external reference bag).
- The stable public identifier `id` exists and is a UUID column on Company,
  Job, Profile and Application (Requirement 18.4 / 19.1 — stable identifiers).
"""

from __future__ import annotations

import pytest
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID

from app.models.application import Application
from app.models.company import Company
from app.models.job import Job
from app.models.profile import Profile
from app.models.user import User

# Models that carry an `external_refs` JSONB bag.
EXTERNAL_REFS_MODELS = [Company, Job, Profile, User, Application]

# Models whose `id` is the stable public UUID identifier.
UUID_ID_MODELS = [Company, Job, Profile, Application]


@pytest.mark.parametrize("model", EXTERNAL_REFS_MODELS, ids=lambda m: m.__name__)
def test_external_refs_is_jsonb_column(model: type) -> None:
    columns = model.__table__.columns
    assert "external_refs" in columns, f"{model.__name__} is missing the external_refs column"

    column = columns["external_refs"]
    assert isinstance(column.type, JSONB), (
        f"{model.__name__}.external_refs should be JSONB, got {column.type!r}"
    )
    assert column.nullable is False, f"{model.__name__}.external_refs should be NOT NULL"


@pytest.mark.parametrize("model", UUID_ID_MODELS, ids=lambda m: m.__name__)
def test_id_is_uuid_primary_key(model: type) -> None:
    columns = model.__table__.columns
    assert "id" in columns, f"{model.__name__} is missing the id column"

    column = columns["id"]
    assert isinstance(column.type, PGUUID), (
        f"{model.__name__}.id should be a UUID column, got {column.type!r}"
    )
    assert column.primary_key is True, f"{model.__name__}.id should be the primary key"
