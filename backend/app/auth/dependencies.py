from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.jwt import TokenPayload, decode_token
from app.database import get_db
import app.models as models

bearer_scheme = HTTPBearer(auto_error=False)


def load_user_by_id(db: Any, user_id: str):
    user_model = getattr(models, "User", None)
    if user_model is None:
        return None
    if hasattr(db, "get"):
        try:
            user = db.get(user_model, user_id)
            if user is not None:
                return user
        except TypeError:
            pass
    id_field = getattr(user_model, "id", None) or getattr(user_model, "_id", None)
    if id_field is None:
        return None
    return db.query(user_model).filter(id_field == user_id).first()


def get_user_id(user: Any) -> str | None:
    return getattr(user, "id", None) or getattr(user, "_id", None)


def get_user_roles(user: Any) -> list[str]:
    roles = getattr(user, "roles", None) or []
    if isinstance(roles, str):
        return [roles]
    return list(roles)


def is_admin_user(user: Any) -> bool:
    return "admin" in get_user_roles(user)


def get_primary_email(user: Any) -> str | None:
    direct = getattr(user, "email", None)
    if direct:
        return direct
    emails = getattr(user, "emails", None)
    if isinstance(emails, list) and emails:
        first = emails[0]
        if isinstance(first, dict):
            return first.get("address")
        return getattr(first, "address", None)
    for attr in ("google_email", "facebook_email", "github_email", "twitter_email"):
        value = getattr(user, attr, None)
        if value:
            return value
    return None


def is_email_verified(user: Any) -> bool:
    verified = getattr(user, "email_verified", None)
    if verified is not None:
        return bool(verified)
    emails = getattr(user, "emails", None)
    if isinstance(emails, list) and emails:
        first = emails[0]
        if isinstance(first, dict):
            if first.get("verified") is not None:
                return bool(first.get("verified"))
        else:
            attr = getattr(first, "verified", None)
            if attr is not None:
                return bool(attr)
    has_oauth_identity = bool(getattr(user, "oauth_providers", None)) or any(
        getattr(user, attr, None) for attr in ("google_id", "facebook_id", "github_id", "twitter_id", "oauth_provider")
    )
    if has_oauth_identity:
        return True
    # EMP-022: previously `oauth_only or not email` returned True for a row
    # with NO email and NO OAuth identity, letting a malformed/legacy row
    # pass email-verified gates (job posting, payments). Such rows are not
    # verified.
    return False


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def _get_password_changed_at(user: Any):
    return getattr(user, "password_changed_at", None) or getattr(user, "passwordChangedAt", None)


def _decode_bearer(
    credentials: HTTPAuthorizationCredentials | None,
    password_changed_at=None,
) -> TokenPayload:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    try:
        return decode_token(
            credentials.credentials,
            expected_type="access",
            password_changed_at=password_changed_at,
        )
    except ValueError as exc:
        raise _unauthorized("Invalid access token") from exc


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Any = Depends(get_db),
):
    payload = _decode_bearer(credentials)
    user = load_user_by_id(db, payload.sub)
    if user is None:
        raise _unauthorized("User not found")
    _decode_bearer(credentials, password_changed_at=_get_password_changed_at(user))
    return user


def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Any = Depends(get_db),
):
    if credentials is None:
        return None
    payload = _decode_bearer(credentials)
    user = load_user_by_id(db, payload.sub)
    if user is None:
        return None
    _decode_bearer(credentials, password_changed_at=_get_password_changed_at(user))
    return user


def require_admin(user: Any = Depends(get_current_user)):
    if not is_admin_user(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


def require_email_verified(user: Any = Depends(get_current_user)):
    if not is_email_verified(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email verification required")
    return user
