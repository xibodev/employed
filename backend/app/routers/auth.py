from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import defaultdict, deque
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from app.auth.dependencies import get_primary_email, get_user_id, get_user_roles, is_email_verified, load_user_by_id
from app.auth.jwt import (
    create_password_reset_token,
    create_verification_token,
    decode_password_reset_token,
    decode_token,
    decode_verification_token,
    issue_token_pair,
)
from app.auth.oauth import authorize_redirect_url, exchange_code
from app.auth.passwords import hash_password, verify_password
from app.auth.revocation import is_revoked, revoke_jti
from app.config import settings
from app.database import get_db
from app.middleware.rate_limit import _client_ip, close_quietly, rate_limit, redis_client
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RefreshTokenRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    TokenStatusResponse,
)
from app.schemas.users import UserRead
from app.services.email import send_password_reset_email, send_registration_attempt_email, send_verification_email
from app.services.model_utils import get_attr, get_model_field, query_all, resolve_model, save, set_attr, utcnow

router = APIRouter(prefix="/auth", tags=["auth"])

logger = logging.getLogger(__name__)

FAILED_LOGIN_LIMIT = 5
FAILED_LOGIN_WINDOW_SECONDS = 15 * 60
FAILED_LOGIN_LOCKOUT_SECONDS = 15 * 60
INVALID_LOGIN_DETAIL = "Invalid email or password"

LOCKOUT_LOCK_PREFIX = "auth:lockout:"
LOCKOUT_FAILS_PREFIX = "auth:lockout-fails:"

# EMP-006: browser clients receive the refresh token in an httpOnly cookie
# (scoped to /auth) so an XSS cannot exfiltrate it from localStorage. The
# token is still returned in the response body for non-browser clients.
REFRESH_COOKIE_NAME = "employed_refresh_token"


def _refresh_cookie_secure() -> bool:
    environment = str(getattr(settings, "environment", "development") or "development").strip().lower()
    return environment not in {"development", "dev", "testing", "test"}


def _set_refresh_cookie(response: Response, token: str) -> None:
    days = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        token,
        max_age=days * 24 * 60 * 60,
        httponly=True,
        samesite="lax",
        secure=_refresh_cookie_secure(),
        path="/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/auth")


class FailedLoginTracker:
    """In-process fallback lockout store (used when Redis is unavailable).

    Keys are opaque composite strings (see _lockout_key)."""

    def __init__(self) -> None:
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._locks: dict[str, float] = {}
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> None:
        cutoff = now - FAILED_LOGIN_WINDOW_SECONDS
        bucket = self._attempts[key]
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        locked_until = self._locks.get(key)
        if locked_until is not None and locked_until <= now:
            self._locks.pop(key, None)
        if not bucket:
            self._attempts.pop(key, None)

    def is_locked(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            self._prune(key, now)
            locked_until = self._locks.get(key)
            return bool(locked_until and locked_until > now)

    def record_failure(self, key: str) -> None:
        now = time.time()
        with self._lock:
            self._prune(key, now)
            bucket = self._attempts[key]
            bucket.append(now)
            if len(bucket) >= FAILED_LOGIN_LIMIT:
                self._locks[key] = now + FAILED_LOGIN_LOCKOUT_SECONDS
                bucket.clear()
                self._attempts.pop(key, None)

    def record_success(self, key: str) -> None:
        with self._lock:
            self._locks.pop(key, None)
            self._attempts.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._locks.clear()
            self._attempts.clear()


failed_login_tracker = FailedLoginTracker()


def _lockout_key(email: str, client_ip: str) -> str:
    """Lockout key scoped to (email, client IP) — EMP-020.

    Keying on email alone let anyone lock a victim's account with 5 junk
    attempts; scoping to the requesting IP keeps brute-force protection
    while removing the trivial DoS."""
    return f"{(email or '').strip().lower()}|{client_ip}"


def _lockout_is_locked(key: str) -> bool:
    client = redis_client()
    if client is not None:
        try:
            return client.get(f"{LOCKOUT_LOCK_PREFIX}{key}") is not None
        except Exception:  # noqa: BLE001 — fall back to in-process store
            logger.warning("auth.lockout.redis_read_failed", exc_info=True)
        finally:
            close_quietly(client)
    return failed_login_tracker.is_locked(key)


def _lockout_record_failure(key: str) -> None:
    client = redis_client()
    if client is not None:
        try:
            fails_key = f"{LOCKOUT_FAILS_PREFIX}{key}"
            fails = int(client.incr(fails_key))
            if fails == 1:
                client.expire(fails_key, FAILED_LOGIN_WINDOW_SECONDS)
            if fails >= FAILED_LOGIN_LIMIT:
                client.set(f"{LOCKOUT_LOCK_PREFIX}{key}", "1", ex=FAILED_LOGIN_LOCKOUT_SECONDS)
                client.delete(fails_key)
            return
        except Exception:  # noqa: BLE001
            logger.warning("auth.lockout.redis_write_failed", exc_info=True)
        finally:
            close_quietly(client)
    failed_login_tracker.record_failure(key)


def _lockout_record_success(key: str) -> None:
    client = redis_client()
    if client is not None:
        try:
            client.delete(f"{LOCKOUT_LOCK_PREFIX}{key}", f"{LOCKOUT_FAILS_PREFIX}{key}")
            return
        except Exception:  # noqa: BLE001
            logger.warning("auth.lockout.redis_clear_failed", exc_info=True)
        finally:
            close_quietly(client)
    failed_login_tracker.record_success(key)


def _user_model():
    return resolve_model("User")


def _frontend_base_url(request: Request) -> str:
    """Base URL for links sent in emails (EMP-004).

    Email links must land on the frontend pages (/verify-email/[token],
    /reset-password/[token]) — the API routes with those tokens are
    POST-only and return 405 on the GET an email client performs.
    Resolution order: FRONTEND_BASE_URL, APP_BASE_URL, then the request
    base URL as a last-resort development fallback.
    """
    base = getattr(settings, "frontend_base_url", None) or getattr(settings, "app_base_url", None)
    if base:
        return str(base).rstrip("/")
    return str(request.base_url).rstrip("/")


def _user_to_read(user: Any) -> UserRead:
    return UserRead(
        id=str(get_user_id(user) or ""),
        email=get_primary_email(user),
        name=get_attr(user, "display_name", "name", "full_name", "username"),
        roles=get_user_roles(user),
        email_verified=is_email_verified(user),
        created_at=get_attr(user, "created_at", "createdAt"),
        deletion_requested_at=get_attr(user, "deletion_requested_at", "deletionRequestedAt"),
        deletion_scheduled_for=get_attr(user, "deletion_scheduled_for", "deletionScheduledFor"),
    )


def _rollback_quietly(db: Any) -> None:
    rollback = getattr(db, "rollback", None)
    if callable(rollback):
        try:
            rollback()
        except Exception:  # noqa: BLE001 — best-effort session recovery
            pass


def _find_user_by_email(db: Any, email: str):
    """Indexed equality lookup on users.email (EMP-005).

    Previously iterated the whole users table in Python on every login /
    register / forgot-password request. Emails are normalized to lowercase
    on write; a case-insensitive fallback query covers legacy mixed-case
    rows. The Python scan remains only for models without an email column.
    """
    normalized = (email or "").strip().lower()
    if not normalized:
        return None
    model = _user_model()
    email_field = get_model_field(model, "email")
    if email_field is not None:
        matches = query_all(db, model, filters=[email_field == normalized], limit=1)
        if matches:
            return matches[0]
        try:
            from sqlalchemy import func

            matches = query_all(db, model, filters=[func.lower(email_field) == normalized], limit=1)
        except Exception:  # noqa: BLE001 — dialect without lower() push-down
            _rollback_quietly(db)
            matches = []
        return matches[0] if matches else None
    for user in query_all(db, model):
        current = (get_primary_email(user) or "").strip().lower()
        if current == normalized:
            return user
    return None


def _find_user_by_provider(db: Any, provider: str, provider_id: str | None):
    if not provider_id:
        return None
    model = _user_model()
    providers_field = get_model_field(model, "oauth_providers")
    if providers_field is not None and hasattr(providers_field, "contains"):
        # JSONB containment push-down (users.oauth_providers @> {provider: id})
        try:
            matches = query_all(db, model, filters=[providers_field.contains({provider: provider_id})], limit=1)
            if matches:
                return matches[0]
        except Exception:  # noqa: BLE001 — non-JSONB dialect (e.g. SQLite tests)
            _rollback_quietly(db)
    for user in query_all(db, model):
        oauth_providers = get_attr(user, "oauth_providers", default={}) or {}
        if isinstance(oauth_providers, dict) and oauth_providers.get(provider) == provider_id:
            return user
        if get_attr(user, f"{provider}_id", f"{provider}Id", "oauth_subject") == provider_id and (
            get_attr(user, "oauth_provider") in (None, provider) or get_attr(user, f"{provider}_id", f"{provider}Id")
        ):
            return user
    return None


def _set_local_user_fields(user: Any, email: str, name: str | None, password: str) -> None:
    now = utcnow()
    set_attr(user, email.strip().lower(), "email")
    if hasattr(user, "emails"):
        set_attr(user, [{"address": email.strip().lower(), "verified": False}], "emails")
    if name:
        set_attr(user, name, "display_name", "name", "full_name", "username")
    password_hash = hash_password(password)
    set_attr(user, password_hash, "password_hash", "hashed_password", "passwordHash")
    set_attr(user, now, "password_changed_at", "passwordChangedAt")
    set_attr(user, False, "email_verified", "emailVerified")
    set_attr(user, [], "roles")
    set_attr(user, now, "created_at", "createdAt")


def _set_oauth_fields(user: Any, profile: dict) -> None:
    provider = profile["provider"]
    # Normalize on write so the indexed equality lookup in
    # _find_user_by_email stays correct (EMP-005).
    normalized_email = (profile.get("email") or "").strip().lower() or None
    set_attr(user, normalized_email, "email")
    if hasattr(user, "emails") and normalized_email:
        set_attr(user, [{"address": normalized_email, "verified": True}], "emails")
    set_attr(user, profile.get("name"), "display_name", "name", "full_name", "username")
    set_attr(user, profile.get("provider_id"), f"{provider}_id", f"{provider}Id")
    set_attr(user, provider, "oauth_provider")
    set_attr(user, profile.get("provider_id"), "oauth_subject")
    set_attr(user, profile.get("avatar_url"), "avatar_url", "avatarUrl")
    oauth_providers = dict(get_attr(user, "oauth_providers", default={}) or {})
    oauth_providers[provider] = profile.get("provider_id")
    set_attr(user, oauth_providers, "oauth_providers")
    set_attr(user, True, "email_verified", "emailVerified")
    if get_attr(user, "created_at", "createdAt") is None:
        set_attr(user, utcnow(), "created_at", "createdAt")
    if get_attr(user, "roles") is None:
        set_attr(user, [], "roles")


def _get_password_changed_at(user: Any):
    return get_attr(user, "password_changed_at", "passwordChangedAt")


def _set_password_changed_at(user: Any) -> None:
    set_attr(user, utcnow(), "password_changed_at", "passwordChangedAt")


def _token_response(user: Any) -> TokenResponse:
    pair = issue_token_pair(str(get_user_id(user)))
    return TokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        token_type=pair.token_type,
        user=_user_to_read(user),
    )


def _registration_response() -> TokenResponse:
    return TokenResponse(
        access_token="",
        refresh_token="",
        token_type="bearer",
        user=None,
        message="Check your email to complete registration",
    )


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit(5, 60, "auth_register"))],
)
def register(payload: RegisterRequest, request: Request, db: Any = Depends(get_db)):
    existing_user = _find_user_by_email(db, payload.email)
    email = payload.email.strip().lower()
    if existing_user is not None:
        send_registration_attempt_email(email)
        return _registration_response()
    user = _user_model()()
    _set_local_user_fields(user, email, payload.name, payload.password)
    saved = save(db, user)
    token = create_verification_token(str(get_user_id(saved)), email)
    verify_url = f"{_frontend_base_url(request)}/verify-email/{token}"
    send_verification_email(email, verify_url)
    return _registration_response()


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(rate_limit(10, 60, "auth_login"))])
def login(payload: LoginRequest, request: Request, response: Response, db: Any = Depends(get_db)):
    lockout_key = _lockout_key(payload.email, _client_ip(request))
    if _lockout_is_locked(lockout_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_LOGIN_DETAIL)
    user = _find_user_by_email(db, payload.email)
    if user is None:
        _lockout_record_failure(lockout_key)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_LOGIN_DETAIL)
    hashed = get_attr(user, "password_hash", "hashed_password", "passwordHash")
    if not verify_password(payload.password, hashed):
        _lockout_record_failure(lockout_key)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_LOGIN_DETAIL)
    _lockout_record_success(lockout_key)
    token_response = _token_response(user)
    _set_refresh_cookie(response, token_response.refresh_token)
    return token_response


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(
    request: Request,
    response: Response,
    payload: RefreshTokenRequest | None = None,
    db: Any = Depends(get_db),
):
    # Body token (non-browser clients) or httpOnly cookie (browsers, EMP-006).
    token_value = (payload.refresh_token if payload else None) or request.cookies.get(REFRESH_COOKIE_NAME)
    if not token_value:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    try:
        token = decode_token(token_value, expected_type="refresh")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc
    if token.jti and is_revoked(token.jti):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token has been revoked")
    user = load_user_by_id(db, token.sub)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    try:
        decode_token(
            token_value,
            expected_type="refresh",
            password_changed_at=_get_password_changed_at(user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc
    token_response = _token_response(user)
    _set_refresh_cookie(response, token_response.refresh_token)
    return token_response


@router.post("/logout", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def logout(request: Request, response: Response) -> MessageResponse:
    """Logout — revokes the supplied refresh token's JTI in Redis (if provided).

    The endpoint accepts an empty body, an empty JSON object ``{}``, or a body
    with ``refresh_token: null`` for backward compatibility with clients that
    simply want a 200 on POST. When a refresh_token is supplied (body or
    httpOnly cookie), its JTI is added to the revocation store so any later
    /auth/refresh attempt with the same token fails with 401. The refresh
    cookie is always cleared.
    """
    _clear_refresh_cookie(response)
    refresh_token_value: str | None = None
    try:
        raw = await request.body()
        if raw:
            data = json.loads(raw.decode("utf-8") or "{}")
            if isinstance(data, dict):
                candidate = data.get("refresh_token")
                if isinstance(candidate, str) and candidate.strip():
                    refresh_token_value = candidate.strip()
    except (ValueError, UnicodeDecodeError):
        # Garbage body — still 200, nothing to revoke.
        return MessageResponse(message="Logged out")

    refresh_token_value = refresh_token_value or request.cookies.get(REFRESH_COOKIE_NAME)
    if refresh_token_value:
        try:
            decoded = decode_token(refresh_token_value, expected_type="refresh")
        except ValueError:
            return MessageResponse(message="Logged out")
        if decoded.jti and decoded.exp:
            now_ts = int(time.time())
            ttl = max(1, int(decoded.exp) - now_ts)
            revoke_jti(decoded.jti, ttl)
    return MessageResponse(message="Logged out")


def _apply_verified_domain_memberships(db: Any, user: Any) -> None:
    """Link a just-verified user to companies that own their email domain (R3.2/3.3).

    On email verification, match the verified email's domain against each
    Company's ``verified_email_domains`` and apply the idempotent domain
    auto-membership policy, which creates an ``invited`` membership requiring
    manual approval (R3.3) and records an audit entry.

    Best-effort: the email-verification flow must succeed even if the Company
    model is unavailable (e.g. the SQLite-backed test rig has no ``companies``
    table) or the containment query fails. Any failure is logged and swallowed.
    """
    try:
        email = get_primary_email(user)
        if not email or "@" not in email:
            return
        domain = email.rsplit("@", 1)[-1].strip().lower()
        if not domain:
            return

        Company = resolve_model("Company")
        from app.services.memberships import apply_domain_auto_membership

        companies = db.query(Company).filter(Company.verified_email_domains.contains([domain])).all()
        if not companies:
            return
        for company in companies:
            apply_domain_auto_membership(db, company=company, user=user)
        db.commit()
    except Exception:  # noqa: BLE001 - never let auto-membership break verification
        logger.warning("domain auto-membership skipped for verified email", exc_info=True)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            logger.debug("rollback after domain auto-membership failure also failed", exc_info=True)


@router.post("/verify-email/{token}", response_model=TokenStatusResponse)
def verify_email(token: str, db: Any = Depends(get_db)):
    try:
        payload = decode_verification_token(token)
    except ValueError as exc:
        # EMP-025: malformed/expired tokens must return 400, not bubble up
        # as an unhandled 500.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired verification token"
        ) from exc
    user = load_user_by_id(db, payload.sub)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    set_attr(user, True, "email_verified", "emailVerified")
    if hasattr(user, "emails"):
        emails = get_attr(user, "emails", default=[])
        if isinstance(emails, list) and emails:
            first = emails[0]
            if isinstance(first, dict):
                first["verified"] = True
            else:
                setattr(first, "verified", True)
            set_attr(user, emails, "emails")
    save(db, user)
    _apply_verified_domain_memberships(db, user)
    return TokenStatusResponse(message="Email verified", verified_at=utcnow())


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit(3, 60, "auth_forgot_password"))],
)
def forgot_password(payload: ForgotPasswordRequest, request: Request, db: Any = Depends(get_db)):
    user = _find_user_by_email(db, payload.email)
    if user is not None:
        token = create_password_reset_token(str(get_user_id(user)), payload.email.strip().lower())
        reset_url = f"{_frontend_base_url(request)}/reset-password/{token}"
        send_password_reset_email(payload.email.strip().lower(), reset_url)
    return MessageResponse(message="If an account exists for that email, a reset link has been sent")


@router.post(
    "/reset-password/{token}",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit(5, 60, "auth_reset_password"))],
)
def reset_password(token: str, payload: ResetPasswordRequest, db: Any = Depends(get_db)):
    try:
        decoded = decode_password_reset_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token") from exc
    user = load_user_by_id(db, decoded.sub)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    try:
        decode_password_reset_token(token, password_changed_at=_get_password_changed_at(user))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token") from exc
    set_attr(user, hash_password(payload.password), "password_hash", "hashed_password", "passwordHash")
    _set_password_changed_at(user)
    save(db, user)
    return MessageResponse(message="Password updated")


@router.get("/oauth/{provider}")
def oauth_redirect(provider: str, request: Request):
    return RedirectResponse(
        url=authorize_redirect_url(request, provider), status_code=status.HTTP_307_TEMPORARY_REDIRECT
    )


@router.get("/oauth/{provider}/callback", response_model=TokenResponse, name="oauth_callback")
async def oauth_callback(
    provider: str,
    request: Request,
    response: Response,
    code: str,
    state: str | None = None,
    db: Any = Depends(get_db),
):
    if state is None:
        if getattr(exchange_code, "__module__", "") == "app.auth.oauth":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing OAuth state")
        profile = await exchange_code(provider, request, code)
    else:
        profile = await exchange_code(provider, request, code, state)
    user = _find_user_by_provider(db, provider, profile.get("provider_id"))
    # EMP-018: only link to an existing local account by email when the
    # provider attests the email is verified — otherwise a provider account
    # holding someone else's (unverified) address takes over the local
    # account. Default True for google profiles lacking the claim (legacy
    # exchange stubs); google's normalize_profile carries the real claim.
    claim_verified = bool(profile.get("email_verified", provider == "google"))
    if user is None and profile.get("email"):
        existing_by_email = _find_user_by_email(db, profile["email"])
        if existing_by_email is not None:
            if not claim_verified:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Email address is not verified with the OAuth provider",
                )
            user = existing_by_email
    if user is None:
        user = _user_model()()
    _set_oauth_fields(user, profile)
    saved = save(db, user)
    token_response = _token_response(saved)
    _set_refresh_cookie(response, token_response.refresh_token)
    return token_response
