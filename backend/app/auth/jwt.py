from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
import uuid
from typing import Any

from jose import JWTError, jwt
from pydantic import BaseModel

from app.config import settings


class TokenPayload(BaseModel):
    sub: str
    type: str
    exp: int | None = None
    iat: int | None = None
    jti: str | None = None
    email: str | None = None


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class VerificationTokenPayload(BaseModel):
    sub: str
    email: str
    type: str = "verify_email"
    exp: int | None = None
    iat: int | None = None


class PasswordResetTokenPayload(BaseModel):
    sub: str
    email: str
    type: str = "reset_password"
    exp: int | None = None
    iat: int | None = None


def _setting(*names: str, default: Any = None) -> Any:
    for name in names:
        value = getattr(settings, name, getattr(settings, name.lower(), None))
        if value not in (None, ""):
            return value
        env_value = os.getenv(name)
        if env_value not in (None, ""):
            return env_value
    return default


def _environment() -> str:
    return str(getattr(settings, "environment", "development") or "development").strip().lower()


def ensure_jwt_secret_configured() -> None:
    if _setting("JWT_SECRET_KEY", "SECRET_KEY", "secret_key") in (None, "") and _environment() not in {
        "testing",
        "test",
    }:
        raise RuntimeError("SECRET_KEY must be configured before starting the application")


def _secret_key() -> str:
    ensure_jwt_secret_configured()
    secret = _setting("JWT_SECRET_KEY", "SECRET_KEY", "secret_key")
    if secret in (None, ""):
        raise RuntimeError("SECRET_KEY must be configured before starting the application")
    return str(secret)


def _algorithm() -> str:
    return str(_setting("JWT_ALGORITHM", default="HS256"))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _create_token(subject: str, token_type: str, expires_delta: timedelta, extra: dict[str, Any] | None = None) -> str:
    now = _utcnow()
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "exp": now + expires_delta,
        "iat": now,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, _secret_key(), algorithm=_algorithm())


def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    minutes = int(_setting("ACCESS_TOKEN_EXPIRE_MINUTES", default=30))
    return _create_token(subject, "access", timedelta(minutes=minutes), extra)


def create_refresh_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    days = int(_setting("REFRESH_TOKEN_EXPIRE_DAYS", default=7))
    payload_extra = dict(extra or {})
    payload_extra.setdefault("jti", uuid.uuid4().hex)
    return _create_token(subject, "refresh", timedelta(days=days), payload_extra)


def create_verification_token(subject: str, email: str) -> str:
    hours = int(_setting("EMAIL_VERIFICATION_EXPIRE_HOURS", default=48))
    return _create_token(subject, "verify_email", timedelta(hours=hours), {"email": email})


def create_password_reset_token(subject: str, email: str) -> str:
    hours = int(_setting("PASSWORD_RESET_EXPIRE_HOURS", default=2))
    return _create_token(subject, "reset_password", timedelta(hours=hours), {"email": email})


def _password_changed_timestamp(password_changed_at: datetime | None) -> int | None:
    if password_changed_at is None:
        return None
    normalized = password_changed_at if password_changed_at.tzinfo else password_changed_at.replace(tzinfo=timezone.utc)
    return int(normalized.astimezone(timezone.utc).timestamp())


def decode_token(
    token: str,
    expected_type: str | None = None,
    password_changed_at: datetime | None = None,
) -> TokenPayload:
    try:
        payload = jwt.decode(token, _secret_key(), algorithms=[_algorithm()])
    except (JWTError, ValueError) as exc:
        # EMP-025: jose can raise raw ValueError (not JWTError) on malformed
        # input such as a truncated/garbage token; normalize everything to
        # ValueError("Invalid token") so callers map it to HTTP 400.
        raise ValueError("Invalid token") from exc
    try:
        data = TokenPayload(**payload)
    except ValueError as exc:  # pydantic ValidationError subclasses ValueError
        raise ValueError("Invalid token") from exc
    if expected_type and data.type != expected_type:
        raise ValueError("Unexpected token type")
    changed_at_ts = _password_changed_timestamp(password_changed_at)
    if changed_at_ts is not None and (data.iat is None or data.iat < changed_at_ts):
        raise ValueError("Token issued before password change")
    return data


def decode_verification_token(token: str) -> VerificationTokenPayload:
    payload = decode_token(token, expected_type="verify_email")
    return VerificationTokenPayload(**payload.model_dump())


def decode_password_reset_token(
    token: str,
    password_changed_at: datetime | None = None,
) -> PasswordResetTokenPayload:
    payload = decode_token(token, expected_type="reset_password", password_changed_at=password_changed_at)
    return PasswordResetTokenPayload(**payload.model_dump())


def issue_token_pair(subject: str, extra: dict[str, Any] | None = None) -> TokenPair:
    return TokenPair(
        access_token=create_access_token(subject, extra=extra),
        refresh_token=create_refresh_token(subject, extra=extra),
    )
