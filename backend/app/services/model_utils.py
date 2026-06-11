from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import app.models as models


def resolve_model(*names: str):
    for name in names:
        model = getattr(models, name, None)
        if model is not None:
            return model
    raise RuntimeError(f"None of the models were found: {', '.join(names)}")


def get_attr(obj: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if hasattr(obj, name):
            value = getattr(obj, name)
            if value is not None:
                return value
    return default


def set_attr(obj: Any, value: Any, *names: str) -> bool:
    for name in names:
        if hasattr(obj, name) or hasattr(type(obj), name):
            setattr(obj, name, value)
            return True
    if names:
        setattr(obj, names[0], value)
        return True
    return False


def get_model_field(model: Any, *names: str):
    for name in names:
        field = getattr(model, name, None)
        if field is not None:
            return field
    return None


def query_all(
    db: Any,
    model: Any,
    *,
    filters: list | None = None,
    order_by: Any = None,
    limit: int | None = None,
    offset: int | None = None,
) -> list[Any]:
    """Return rows from *model*, optionally push-down filtered/ordered/paged.

    When *filters* are supplied they are forwarded directly to SQLAlchemy
    `.filter()` so the database engine handles the predicate instead of
    loading the entire table into Python.  Callers that do not supply any
    keyword arguments get the original behaviour (full-table select).
    """
    query = db.query(model)
    if filters:
        for f in filters:
            query = query.filter(f)
    if order_by is not None:
        query = query.order_by(order_by)
    if offset is not None:
        query = query.offset(offset)
    if limit is not None:
        query = query.limit(limit)
    return list(query.all())


def query_count(db: Any, model: Any, filters: list | None = None) -> int:
    """COUNT(*) push-down companion to query_all (EMP-010)."""
    query = db.query(model)
    if filters:
        for f in filters:
            query = query.filter(f)
    return int(query.count())


def query_by_user(db: Any, model: Any, user_id: Any, *, order_desc: bool = True) -> list[Any]:
    """Return rows from *model* owned by *user_id*, push-down where supported.

    When the model exposes a ``user_id``/``userId`` column we forward the
    predicate (and optional ``created_at`` ordering) to SQLAlchemy so the
    DB handles them. Falls back to a Python-side scan for in-memory test
    rigs whose models do not expose the columns as ORM attributes.
    """
    user_field = get_model_field(model, "user_id", "userId")
    if user_field is not None:
        order_field = get_model_field(model, "created_at", "createdAt")
        order_by = order_field.desc() if (order_desc and order_field is not None) else order_field
        return query_all(db, model, filters=[user_field == user_id], order_by=order_by)
    items = [item for item in query_all(db, model) if get_attr(item, "user_id", "userId") == user_id]
    if order_desc:
        items.sort(key=lambda item: get_attr(item, "created_at", "createdAt", default=utcnow()), reverse=True)
    return items


def get_by_id(db: Any, model: Any, record_id: Any) -> Any | None:
    if hasattr(db, "get"):
        try:
            found = db.get(model, record_id)
            if found is not None:
                return found
        except TypeError:
            pass
    id_field = get_model_field(model, "id", "_id")
    if id_field is None:
        return None
    return db.query(model).filter(id_field == record_id).first()


def save(db: Any, obj: Any) -> Any:
    if hasattr(db, "add"):
        db.add(obj)
    db.commit()
    try:
        db.refresh(obj)
    except Exception:
        pass
    return obj


def delete(db: Any, obj: Any) -> None:
    if hasattr(db, "delete"):
        db.delete(obj)
    db.commit()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
