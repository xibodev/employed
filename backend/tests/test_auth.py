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
    monkeypatch.setattr(
        "app.routers.auth.send_verification_email", lambda email, url: captured.__setitem__("url", url)
    )

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
