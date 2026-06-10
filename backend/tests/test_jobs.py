from __future__ import annotations

from datetime import timedelta

from tests.conftest import utcnow


BASE_JOB_PAYLOAD = {
    "title": "Platform Engineer",
    "company": "Acme",
    "location": "Maputo",
    "url": "https://example.com/jobs/platform-engineer",
    "contact": "jobs@example.com",
    "apply_whatsapp": "258840000000",
    "jobtype": "Full Time",
    "description": "Build reliable systems",
    "remote": False,
}


def test_list_active_jobs_only_within_90_days(client, job_factory, sample_market_headers):
    recent = job_factory(status="active", title="Recent Active")
    job_factory(status="pending", title="Pending Job")
    job_factory(status="active", title="Old Active", created_at=utcnow() - timedelta(days=91))

    response = client.get("/jobs", headers=sample_market_headers("mz"))

    assert response.status_code == 200
    titles = [item["title"] for item in response.json()["items"]]
    assert recent.title in titles
    assert "Pending Job" not in titles
    assert "Old Active" not in titles


def test_list_jobs_with_market_scoping(client, job_factory, sample_market_headers):
    mz_job = job_factory(title="Mozambique Role", country="Mozambique")
    job_factory(title="Mexico Role", country="Mexico")

    response = client.get("/jobs", headers=sample_market_headers("mz"))

    assert response.status_code == 200
    titles = [item["title"] for item in response.json()["items"]]
    assert mz_job.title in titles
    assert "Mexico Role" not in titles


def test_search_by_title_substring_returns_matching_results(client, job_factory, sample_market_headers):
    job_factory(title="Senior Python Developer")
    job_factory(title="Frontend Designer")

    response = client.get("/jobs?query=python", headers=sample_market_headers("mz"))

    assert response.status_code == 200
    assert [item["title"] for item in response.json()["items"]] == ["Senior Python Developer"]


def test_filter_by_job_type_returns_only_matching_type(client, job_factory, sample_market_headers):
    job_factory(title="Contract Role", job_type="Contract")
    job_factory(title="Permanent Role", job_type="Full Time")

    response = client.get("/jobs?jobtype=Contract", headers=sample_market_headers("mz"))

    assert response.status_code == 200
    assert [item["jobtype"] for item in response.json()["items"]] == ["Contract"]


def test_filter_by_remote_returns_only_remote_jobs(client, job_factory, sample_market_headers):
    job_factory(title="Remote Role", remote=True)
    job_factory(title="Office Role", remote=False)

    response = client.get("/jobs?remote=true", headers=sample_market_headers("mz"))

    assert response.status_code == 200
    assert [item["title"] for item in response.json()["items"]] == ["Remote Role"]


def test_pagination_returns_requested_page_size(client, job_factory, sample_market_headers):
    for index in range(15):
        job_factory(title=f"Role {index:02d}")

    response = client.get("/jobs?page=1&page_size=12", headers=sample_market_headers("mz"))

    assert response.status_code == 200
    assert len(response.json()["items"]) == 12


def test_get_job_by_id_returns_full_detail(client, sample_job, sample_market_headers):
    job = sample_job()

    response = client.get(f"/jobs/{job.id}", headers=sample_market_headers("mz"))

    assert response.status_code == 200
    assert response.json()["id"] == job.id
    assert response.json()["contact"] == "jobs@example.com"


def test_get_non_existent_job_returns_404(client, sample_market_headers):
    response = client.get("/jobs/missing-job", headers=sample_market_headers("mz"))

    assert response.status_code == 404


def test_create_job_as_authenticated_user_sets_pending_and_market_country(
    client, test_user, auth_headers, sample_market_headers
):
    response = client.post(
        "/jobs", json=BASE_JOB_PAYLOAD, headers=auth_headers(test_user) | sample_market_headers("mz")
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["country"] == "Mozambique"
    assert body["user_id"] == test_user.id


def test_create_job_anonymously_when_recaptcha_is_bypassed(client, monkeypatch, sample_market_headers):
    async def fake_verify(*args, **kwargs):
        return True

    monkeypatch.setattr("app.routers.jobs._verify_recaptcha", fake_verify)

    response = client.post(
        "/jobs", json={**BASE_JOB_PAYLOAD, "title": "Anonymous Role"}, headers=sample_market_headers("mz")
    )

    assert response.status_code == 201
    assert response.json()["user_id"] is None


def test_update_own_job_returns_200(client, sample_job, test_user, auth_headers, sample_market_headers):
    job = sample_job(user=test_user)

    response = client.put(
        f"/jobs/{job.id}",
        json={"title": "Updated Title", "description": "Updated copy"},
        headers=auth_headers(test_user) | sample_market_headers("mz"),
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Updated Title"


def test_update_someone_elses_job_returns_403(client, sample_job, user_factory, auth_headers, sample_market_headers):
    owner = user_factory(email="owner@example.com")
    other_user = user_factory(email="other@example.com")
    job = sample_job(user=owner)

    response = client.put(
        f"/jobs/{job.id}",
        json={"title": "Unauthorized Edit"},
        headers=auth_headers(other_user) | sample_market_headers("mz"),
    )

    assert response.status_code == 403


def test_delete_own_job_returns_204(client, sample_job, test_user, auth_headers):
    job = sample_job(user=test_user)

    response = client.delete(f"/jobs/{job.id}", headers=auth_headers(test_user))

    assert response.status_code == 204
    assert client.get(f"/jobs/{job.id}").status_code == 404


def test_deactivate_job_as_owner_can_mark_filled(client, sample_job, test_user, auth_headers, sample_market_headers):
    job = sample_job(user=test_user)

    response = client.post(
        f"/jobs/{job.id}/deactivate?filled=true",
        headers=auth_headers(test_user) | sample_market_headers("mz"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "filled"


def test_featured_jobs_returns_only_active_featured_recent_jobs(client, job_factory, sample_market_headers):
    featured = job_factory(title="Featured Role", featured=True)
    job_factory(title="Not Featured", featured=False)
    job_factory(title="Old Featured", featured=True, created_at=utcnow() - timedelta(days=100))

    response = client.get("/jobs/featured", headers=sample_market_headers("mz"))

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [featured.id]


def test_job_count_endpoint_returns_correct_total(client, job_factory, sample_market_headers):
    job_factory(title="Python Engineer")
    job_factory(title="Python Designer")
    job_factory(title="Frontend Engineer")

    response = client.get("/jobs/count?query=python", headers=sample_market_headers("mz"))

    assert response.status_code == 200
    assert response.json()["total"] == 2


def test_recaptcha_secret_resolves_from_settings(monkeypatch):
    """EMP-002 regression: the secret must resolve from the snake_case
    pydantic Settings field (alias RECAPTCHA_SECRET_KEY)."""
    from app.config import settings as app_settings
    from app.routers.jobs import _recaptcha_setting

    monkeypatch.setattr(app_settings, "recaptcha_secret_key", "probe-secret")

    assert _recaptcha_setting("RECAPTCHA_V3_SECRET_KEY", "RECAPTCHA_SECRET_KEY") == "probe-secret"


def test_recaptcha_secret_resolves_from_environment(monkeypatch):
    from app.config import settings as app_settings
    from app.routers.jobs import _recaptcha_setting

    monkeypatch.setattr(app_settings, "recaptcha_secret_key", None)
    monkeypatch.setenv("RECAPTCHA_V3_SECRET_KEY", "env-probe-secret")

    assert _recaptcha_setting("RECAPTCHA_V3_SECRET_KEY", "RECAPTCHA_SECRET_KEY") == "env-probe-secret"


def test_recaptcha_action_contract_accepts_submit_job(monkeypatch):
    """EMP-003 regression: backend accepts the action the frontend widget
    sends ('submit_job') and rejects the legacy mismatched names."""
    from app.routers.jobs import _recaptcha_accepts

    assert _recaptcha_accepts({"success": True, "action": "submit_job", "score": 0.9}) is True
    assert _recaptcha_accepts({"success": True, "action": None, "score": 0.9}) is True
    assert _recaptcha_accepts({"success": True, "action": "create_job", "score": 0.9}) is False
    assert _recaptcha_accepts({"success": True, "action": "edit_job", "score": 0.9}) is False
    assert _recaptcha_accepts({"success": True, "action": "submit_job", "score": 0.1}) is False
    assert _recaptcha_accepts({"success": False, "action": "submit_job", "score": 0.9}) is False


def test_recaptcha_bypass_only_in_development(monkeypatch):
    from app.config import settings as app_settings
    from app.routers.jobs import _recaptcha_bypass_enabled

    monkeypatch.setattr(app_settings, "recaptcha_bypass_in_development", True)
    monkeypatch.setattr(app_settings, "environment", "development")
    assert _recaptcha_bypass_enabled() is True

    monkeypatch.setattr(app_settings, "environment", "production")
    assert _recaptcha_bypass_enabled() is False

    monkeypatch.setattr(app_settings, "recaptcha_bypass_in_development", False)
    monkeypatch.setattr(app_settings, "environment", "development")
    assert _recaptcha_bypass_enabled() is False
