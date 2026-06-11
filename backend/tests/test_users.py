from __future__ import annotations


def test_get_users_me_returns_user_info(client, test_user, auth_headers):
    response = client.get("/users/me", headers=auth_headers(test_user))

    assert response.status_code == 200
    assert response.json()["email"] == test_user.email


def test_export_data_returns_account_jobs_and_profile(
    client, test_user, auth_headers, sample_job, profile_factory, payment_intent_factory, report_factory
):
    job = sample_job(user=test_user)
    profile_factory(user=test_user)
    payment_intent_factory(job=job, user=test_user)
    report_factory(job=job, reporter=test_user)

    response = client.get("/users/me/export", headers=auth_headers(test_user))

    assert response.status_code == 200
    body = response.json()
    assert body["account"]["email"] == test_user.email
    assert len(body["jobs"]) == 1
    assert body["profile"]["user_id"] == test_user.id
    assert len(body["payments"]) == 1
    assert len(body["reports"]) == 1


def test_request_deletion_schedules_account_for_30_days_out(client, test_user, auth_headers):
    response = client.post("/users/me/request-deletion", headers=auth_headers(test_user))

    assert response.status_code == 200
    assert response.json()["scheduled_for"] is not None


def test_cancel_deletion_clears_scheduled_fields(client, test_user, auth_headers):
    client.post("/users/me/request-deletion", headers=auth_headers(test_user))

    response = client.post("/users/me/cancel-deletion", headers=auth_headers(test_user))

    assert response.status_code == 200
    assert response.json()["canceled"] is True


def test_resend_verification_for_unverified_user_returns_200(client, user_factory, auth_headers):
    user = user_factory(email="unverified@example.com", verified=False)

    response = client.post("/users/me/resend-verification", headers=auth_headers(user))

    assert response.status_code == 200
    assert response.json()["message"] == "Verification email sent"


def test_resend_verification_for_verified_user_returns_already_verified(client, test_user, auth_headers):
    response = client.post("/users/me/resend-verification", headers=auth_headers(test_user))

    assert response.status_code == 200
    assert response.json()["message"] == "Email already verified"


def test_is_email_verified_false_for_row_without_email_or_oauth():
    """EMP-022 regression: a malformed/legacy row with no email and no OAuth
    identity must not pass email-verified gates."""
    from types import SimpleNamespace

    from app.auth.dependencies import is_email_verified

    ghost = SimpleNamespace(email=None, email_verified=None, oauth_providers={})
    assert is_email_verified(ghost) is False

    oauth_user = SimpleNamespace(email=None, email_verified=None, oauth_providers={"google": "sub-1"})
    assert is_email_verified(oauth_user) is True

    legacy_oauth = SimpleNamespace(email=None, email_verified=None, oauth_providers={}, google_id="legacy-sub")
    assert is_email_verified(legacy_oauth) is True
