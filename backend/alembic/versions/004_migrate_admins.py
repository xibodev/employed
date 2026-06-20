"""Migrate the legacy platform admin model into RBAC platform roles.

Data migration (no schema changes). Every ``User`` whose ``roles`` array
contains the legacy value ``"admin"`` is mapped to the ``platform_super_admin``
Platform_Role, which carries permissions equivalent to the prior full admin
access (R6.1, R6.2). The migration updates the ``roles`` list in place and never
deletes an account, so every existing administrator is preserved (R6.3). The
mapping is reversible: ``downgrade()`` restores the legacy ``"admin"`` value
(R6.4).

Revision ID: 004_migrate_admins
Revises: 003_rbac_and_tenancy
Create Date: 2026-05-24 02:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "004_migrate_admins"
down_revision = "003_rbac_and_tenancy"
branch_labels = None
depends_on = None

# Legacy free-form role value and the RBAC Platform_Role it maps to.
LEGACY_ADMIN = "admin"
PLATFORM_SUPER_ADMIN = "platform_super_admin"

# Lightweight table reference for the data migration. ``roles`` is a Postgres
# ``text[]`` column (see app/models/user.py), so reads/writes use a Python list.
_users = sa.table(
    "users",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("roles", postgresql.ARRAY(sa.Text())),
)


def _remap_roles(roles: list[str] | None, old: str, new: str) -> list[str] | None:
    """Replace ``old`` with ``new`` in ``roles`` in place, preserving order and
    de-duplicating. Returns the new list, or ``None`` when nothing changed."""
    current = list(roles or [])
    if old not in current:
        return None
    remapped: list[str] = []
    seen: set[str] = set()
    for role in current:
        mapped = new if role == old else role
        if mapped not in seen:
            seen.add(mapped)
            remapped.append(mapped)
    return remapped


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.select(_users.c.id, _users.c.roles)).fetchall()
    for row in rows:
        new_roles = _remap_roles(row.roles, LEGACY_ADMIN, PLATFORM_SUPER_ADMIN)
        if new_roles is not None:
            bind.execute(_users.update().where(_users.c.id == row.id).values(roles=new_roles))


def downgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.select(_users.c.id, _users.c.roles)).fetchall()
    for row in rows:
        new_roles = _remap_roles(row.roles, PLATFORM_SUPER_ADMIN, LEGACY_ADMIN)
        if new_roles is not None:
            bind.execute(_users.update().where(_users.c.id == row.id).values(roles=new_roles))
