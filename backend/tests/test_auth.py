from __future__ import annotations

from datetime import timedelta

from app.auth.jwt import _create_token, create_verification_token


def test_register_with_valid_email_password(client):
    response = client.post(
        "/auth/register",
        json={"email": "new@example.com", "password": "password123", "name": "New User"},
    )

    assert response.status_code == 201
    body = response.json()
    # Registration returns a generic response to prevent email enumeration
    assert body["message"] == "Check your email to complete registration"
    assert body["token_type"] == "bearer"


def test_register_with_duplicate_email_returns_same_response(client):
    """Duplicate registration returns 201 with identical shape to prevent email enumeration."""
    payload = {"email": "dup@example.com", "password": "password123", "name": "Dup User"}
    first = client.post("/auth/register", json=payload)
    assert first.status_code == 201

    second = client.post("/auth/register", json=payload)

    assert second.status_code == 201
    assert second.json()["message"] == "Check your email to complete registration"


def test_login_with_correct_credentials_returns_tokens(client, test_user):
    response = client.post("/auth/login", json={"email": test_user.email, "password": "password123"})

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["user"]["id"] == test_user.id


def test_login_with_wrong_password_returns_401(client, test_user):
    response = client.post("/auth/login", json={"email": test_user.email, "password": "wrong-password"})

    assert response.status_code == 401


def test_refresh_valid_token_returns_new_access_token(client, test_user):
    login = client.post("/auth/login", json={"email": test_user.email, "password": "password123"}).json()

    response = client.post("/auth/refresh", json={"refresh_token": login["refresh_token"]})

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert response.json()["user"]["id"] == test_user.id


def test_refresh_expired_token_returns_401(client, test_user):
    expired = _create_token(test_user.id, "refresh", timedelta(seconds=-1))

    response = client.post("/auth/refresh", json={"refresh_token": expired})

    assert response.status_code == 401


def test_access_protected_route_without_token_returns_401(client):
    response = client.get("/users/me")

    assert response.status_code == 401


def test_access_protected_route_with_valid_token_returns_200(client, test_user, auth_headers):
    response = client.get("/users/me", headers=auth_headers(test_user))

    assert response.status_code == 200
    assert response.json()["id"] == test_user.id


def test_verify_email_with_valid_token_returns_200(client, user_factory):
    user = user_factory(email="verify@example.com", verified=False)
    token = create_verification_token(user.id, user.email)

    response = client.post(f"/auth/verify-email/{token}")

    assert response.status_code == 200
    assert response.json()["message"] == "Email verified"


def test_forgot_password_and_reset_password_flow(client, test_user):
    forgot = client.post("/auth/forgot-password", json={"email": test_user.email})
    assert forgot.status_code == 200

    token = _create_token(test_user.id, "reset_password", timedelta(hours=1), {"email": test_user.email})
    reset = client.post(f"/auth/reset-password/{token}", json={"password": "newpassword123"})
    login = client.post("/auth/login", json={"email": test_user.email, "password": "newpassword123"})

    assert reset.status_code == 200
    assert login.status_code == 200


def test_verify_email_with_invalid_token_returns_400(client):
    # Previously pinned the buggy 500 (unhandled jose error); EMP-025 maps
    # malformed tokens to a clean 400.
    response = client.post("/auth/verify-email/not-a-real-token")

    assert response.status_code == 400


def test_oauth_callback_creates_or_updates_user(client, monkeypatch):
    async def fake_exchange_code(provider: str, request, code: str):
        assert provider == "google"
        assert code == "oauth-code"
        return {
            "provider": "google",
            "provider_id": "google-subject",
            "email": "oauth@example.com",
            "name": "OAuth User",
            "avatar_url": "https://example.com/avatar.png",
        }

    monkeypatch.setattr("app.routers.auth.exchange_code", fake_exchange_code)

    response = client.get("/auth/oauth/google/callback?code=oauth-code")

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == "oauth@example.com"
    assert body["user"]["email_verified"] is True


def test_logout_revokes_refresh_token_jti(client, test_user):
    from app.auth.revocation import reset_memory_store

    reset_memory_store()

    login = client.post("/auth/login", json={"email": test_user.email, "password": "password123"}).json()
    refresh_token = login["refresh_token"]

    logout = client.post("/auth/logout", json={"refresh_token": refresh_token})
    assert logout.status_code == 200

    refresh = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh.status_code == 401
    assert "revoked" in refresh.json()["detail"].lower()


def test_logout_without_body_still_returns_200(client):
    response = client.post("/auth/logout")
    assert response.status_code == 200
    assert response.json()["message"] == "Logged out"


def test_logout_with_empty_json_object_still_returns_200(client):
    # Regression: clients sending Content-Type: application/json + body "{}"
    # must NOT receive 422. Validator-bound RefreshTokenRequest schemas would
    # reject the missing field; the manual JSON parse keeps it permissive.
    response = client.post("/auth/logout", json={})
    assert response.status_code == 200
    assert response.json()["message"] == "Logged out"


def test_logout_with_null_refresh_token_still_returns_200(client):
    response = client.post("/auth/logout", json={"refresh_token": None})
    assert response.status_code == 200


def test_logout_with_invalid_token_still_returns_200(client):
    response = client.post("/auth/logout", json={"refresh_token": "not-a-jwt"})
    assert response.status_code == 200


def test_verification_email_links_to_frontend_page(client, monkeypatch):
    """EMP-004 regression: emailed links must land on the frontend
    /verify-email/[token] page, not the POST-only API route (405 on GET)."""
    from app.config import settings as app_settings

    captured: dict[str, str] = {}

    def fake_send_verification_email(email: str, url: str) -> None:
        captured["url"] = url

    monkeypatch.setattr(app_settings, "frontend_base_url", "https://employed.example")
    monkeypatch.setattr("app.routers.auth.send_verification_email", fake_send_verification_email)

    response = client.post(
        "/auth/register",
        json={"email": "linkcheck@example.com", "password": "password123", "name": "Link Check"},
    )

    assert response.status_code == 201
    assert captured["url"].startswith("https://employed.example/verify-email/")
    assert "/auth/" not in captured["url"]


def test_password_reset_email_links_to_frontend_page(client, test_user, monkeypatch):
    from app.config import settings as app_settings

    captured: dict[str, str] = {}

    def fake_send_password_reset_email(email: str, url: str) -> None:
        captured["url"] = url

    monkeypatch.setattr(app_settings, "frontend_base_url", "https://employed.example")
    monkeypatch.setattr("app.routers.auth.send_password_reset_email", fake_send_password_reset_email)

    response = client.post("/auth/forgot-password", json={"email": test_user.email})

    assert response.status_code == 200
    assert captured["url"].startswith("https://employed.example/reset-password/")
    assert "/auth/" not in captured["url"]


def test_email_link_base_falls_back_to_app_base_url(client, monkeypatch):
    from app.config import settings as app_settings

    captured: dict[str, str] = {}
    monkeypatch.setattr(app_settings, "frontend_base_url", None)
    monkeypatch.setattr(app_settings, "app_base_url", "https://app.employed.example/")
    monkeypatch.setattr("app.routers.auth.send_verification_email", lambda email, url: captured.__setitem__("url", url))

    response = client.post(
        "/auth/register",
        json={"email": "fallback@example.com", "password": "password123", "name": "Fallback"},
    )

    assert response.status_code == 201
    assert captured["url"].startswith("https://app.employed.example/verify-email/")


def test_verify_email_with_garbage_token_returns_400(client):
    """EMP-025 regression: malformed tokens raised an unhandled jose
    ValueError -> 500. Must be a clean 400."""
    response = client.post("/auth/verify-email/not-a-jwt")

    assert response.status_code == 400
    assert "invalid or expired" in response.json()["detail"].lower()


def test_verify_email_with_truncated_token_returns_400(client):
    """A quoted-printable soft line break truncates the JWT mid-signature
    (the exact failure seen in the sealed-stack logs)."""
    token = create_verification_token("some-user-id", "x@example.com")
    response = client.post(f"/auth/verify-email/{token[:60]}")

    assert response.status_code == 400


def test_reset_password_with_garbage_token_returns_400(client):
    response = client.post(
        "/auth/reset-password/not-a-jwt",
        json={"password": "newpassword123"},
    )

    assert response.status_code == 400


def test_find_user_by_email_pushes_filter_to_database(db_session, user_factory):
    """EMP-005 regression: user lookup must be a filtered SELECT, not a
    full-table scan materialized into Python."""
    from sqlalchemy import event

    from app.routers.auth import _find_user_by_email

    user_factory(email="indexed@example.com")
    user_factory(email="someone-else@example.com")

    statements: list[str] = []
    engine = db_session.get_bind()

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        found = _find_user_by_email(db_session, "Indexed@Example.com")
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert found is not None
    assert found.email == "indexed@example.com"
    user_selects = [s for s in statements if s.lower().lstrip().startswith("select") and "users" in s.lower()]
    assert user_selects, "expected at least one SELECT against users"
    assert all("where" in s.lower() for s in user_selects), f"unfiltered users scan detected: {user_selects}"


def test_find_user_by_email_misses_cleanly(db_session, user_factory):
    from app.routers.auth import _find_user_by_email

    user_factory(email="present@example.com")

    assert _find_user_by_email(db_session, "absent@example.com") is None
    assert _find_user_by_email(db_session, "") is None


def test_find_user_by_provider_matches_oauth_providers_map(db_session, user_factory):
    from app.routers.auth import _find_user_by_provider

    user = user_factory(email="oauth-map@example.com", oauth_providers={"google": "sub-123"})
    user_factory(email="oauth-other@example.com", oauth_providers={"google": "sub-456"})

    found = _find_user_by_provider(db_session, "google", "sub-123")

    assert found is not None
    assert found.id == user.id
    assert _find_user_by_provider(db_session, "google", "missing-sub") is None


def test_lockout_is_scoped_to_attacker_ip_not_just_email(client, test_user, monkeypatch):
    """EMP-020 regression: 5 junk attempts from one IP must not lock the
    victim's account for everyone (trivial DoS when keyed by email only)."""
    monkeypatch.setattr("app.routers.auth._client_ip", lambda request: "203.0.113.66")
    for _ in range(5):
        response = client.post("/auth/login", json={"email": test_user.email, "password": "wrong-password"})
        assert response.status_code == 401

    # Attacker IP is locked out even with correct credentials
    locked = client.post("/auth/login", json={"email": test_user.email, "password": "password123"})
    assert locked.status_code == 401

    # The victim logging in from their own IP is unaffected
    monkeypatch.setattr("app.routers.auth._client_ip", lambda request: "198.51.100.20")
    victim = client.post("/auth/login", json={"email": test_user.email, "password": "password123"})
    assert victim.status_code == 200


def test_lockout_clears_on_successful_login(client, test_user, monkeypatch):
    monkeypatch.setattr("app.routers.auth._client_ip", lambda request: "198.51.100.30")
    for _ in range(3):
        client.post("/auth/login", json={"email": test_user.email, "password": "wrong-password"})

    ok = client.post("/auth/login", json={"email": test_user.email, "password": "password123"})
    assert ok.status_code == 200

    # Counter was reset: three more failures do not lock yet
    for _ in range(3):
        client.post("/auth/login", json={"email": test_user.email, "password": "wrong-password"})
    again = client.post("/auth/login", json={"email": test_user.email, "password": "password123"})
    assert again.status_code == 200


def test_login_sets_httponly_refresh_cookie(client, test_user):
    """EMP-006: browsers get the refresh token in an httpOnly cookie scoped
    to /auth so XSS cannot read it from localStorage."""
    response = client.post("/auth/login", json={"email": test_user.email, "password": "password123"})

    assert response.status_code == 200
    set_cookie = response.headers.get("set-cookie", "")
    assert "employed_refresh_token=" in set_cookie
    assert "httponly" in set_cookie.lower()
    assert "path=/auth" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()


def test_refresh_works_with_cookie_only(client, test_user):
    login = client.post("/auth/login", json={"email": test_user.email, "password": "password123"})
    assert login.status_code == 200

    # No body token — the TestClient session carries the httpOnly cookie.
    response = client.post("/auth/refresh", json={})

    assert response.status_code == 200
    assert response.json()["access_token"]


def test_refresh_without_body_or_cookie_returns_401(client):
    response = client.post("/auth/refresh", json={})

    assert response.status_code == 401


def test_logout_revokes_cookie_refresh_token_and_clears_cookie(client, test_user):
    from app.auth.revocation import reset_memory_store

    reset_memory_store()

    login = client.post("/auth/login", json={"email": test_user.email, "password": "password123"})
    refresh_token_value = login.json()["refresh_token"]

    logout = client.post("/auth/logout")
    assert logout.status_code == 200
    set_cookie = logout.headers.get("set-cookie", "")
    assert "employed_refresh_token=" in set_cookie  # deletion cookie

    # The JTI from the cookie-carried token is revoked
    refresh = client.post("/auth/refresh", json={"refresh_token": refresh_token_value})
    assert refresh.status_code == 401


def test_oauth_links_existing_account_only_with_verified_email_claim(client, user_factory, monkeypatch):
    """EMP-018 regression: email-based account linking requires the
    provider's verified-email attestation."""
    victim = user_factory(email="victim@example.com")

    async def unverified_exchange(provider: str, request, code: str):
        return {
            "provider": "google",
            "provider_id": "attacker-subject",
            "email": "victim@example.com",
            "email_verified": False,
            "name": "Attacker",
        }

    monkeypatch.setattr("app.routers.auth.exchange_code", unverified_exchange)

    response = client.get("/auth/oauth/google/callback?code=oauth-code")

    # The takeover attempt is rejected outright (no duplicate account is
    # possible either: users.email is unique).
    assert response.status_code == 403
    assert "not verified" in response.json()["detail"].lower()
    assert victim.email == "victim@example.com"


def test_oauth_links_existing_account_with_verified_email_claim(client, user_factory, monkeypatch):
    existing = user_factory(email="linked@example.com")

    async def verified_exchange(provider: str, request, code: str):
        return {
            "provider": "google",
            "provider_id": "google-linked-subject",
            "email": "linked@example.com",
            "email_verified": True,
            "name": "Linked User",
        }

    monkeypatch.setattr("app.routers.auth.exchange_code", verified_exchange)

    response = client.get("/auth/oauth/google/callback?code=oauth-code")

    assert response.status_code == 200
    assert response.json()["user"]["id"] == existing.id
