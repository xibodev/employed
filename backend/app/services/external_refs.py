"""Read/write helpers for the ``external_refs`` JSONB mapping (R19).

Every major entity (Company, Job, Profile, User, Application) carries an
``external_refs`` JSONB column declared as ``MutableDict.as_mutable(JSONB)``
(DD-8). Because the column is a SQLAlchemy ``MutableDict``, mutating the mapping
in place flags the attribute dirty so the change is flushed on commit — adding
or updating an external identifier is a plain JSONB write and never requires a
schema migration (R19.2).

These helpers centralise that read/write pattern so callers (e.g. the export
API and integration code) do not duplicate the dirty-tracking bookkeeping.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.application import Application
    from app.models.company import Company
    from app.models.job import Job
    from app.models.profile import Profile
    from app.models.user import User

    # Any entity that exposes an ``external_refs`` JSONB mapping.
    ExternalRefEntity = Company | Job | Profile | User | Application


def get_external_refs(entity: Any) -> dict[str, Any]:
    """Return a shallow copy of *entity*'s ``external_refs`` mapping.

    A copy is returned so callers cannot mutate the tracked attribute by
    accident; use :func:`set_external_ref` to persist changes.
    """
    refs = getattr(entity, "external_refs", None)
    if not refs:
        return {}
    return dict(refs)


def get_external_ref(entity: Any, system: str, default: Any = None) -> Any:
    """Return the external identifier stored for *system*, or *default*."""
    refs = getattr(entity, "external_refs", None)
    if not refs:
        return default
    return refs.get(system, default)


def set_external_ref(
    db: Session,
    entity: Any,
    system: str,
    value: Any,
    *,
    commit: bool = True,
) -> Any:
    """Write ``external_refs[system] = value`` on *entity* and persist it.

    The write relies on ``MutableDict`` semantics: mutating the mapping in
    place marks the attribute dirty so SQLAlchemy emits the JSONB update on the
    next flush — no migration required (R19.2). When *entity* has no mapping yet
    (legacy ``NULL`` rows), a fresh dict is assigned, which the column coerces
    back into a tracked ``MutableDict``.

    Pass ``commit=False`` to batch several writes inside an outer transaction;
    the default commits immediately.
    """
    refs = getattr(entity, "external_refs", None)
    if refs is None:
        entity.external_refs = {system: value}
    else:
        refs[system] = value
    db.add(entity)
    if commit:
        db.commit()
        db.refresh(entity)
    else:
        db.flush()
    return entity


def delete_external_ref(
    db: Session,
    entity: Any,
    system: str,
    *,
    commit: bool = True,
) -> Any:
    """Remove *system* from *entity*'s ``external_refs`` if present.

    A missing key is a no-op so the operation is idempotent.
    """
    refs = getattr(entity, "external_refs", None)
    if refs and system in refs:
        del refs[system]
        db.add(entity)
        if commit:
            db.commit()
            db.refresh(entity)
        else:
            db.flush()
    return entity
