from __future__ import annotations


def test_non_admin_access_to_admin_endpoints_returns_403(client, test_user, auth_headers):
    response = client.get("/admin/jobs", headers=auth_headers(test_user))

    assert response.status_code == 403


def test_admin_list_jobs_filtered_by_status(client, test_admin, auth_headers, job_factory):
    job_factory(status="pending", title="Pending Review")
    job_factory(status="active", title="Live Job")

    response = client.get("/admin/jobs?status=pending", headers=auth_headers(test_admin))

    assert response.status_code == 200
    assert [item["title"] for item in response.json()["items"]] == ["Pending Review"]


def test_admin_set_job_status_updates_status_history(client, test_admin, auth_headers, sample_job, db_session):
    job = sample_job(status="pending")

    response = client.patch(
        f"/admin/jobs/{job.id}/status",
        json={"status": "active", "reason": "Looks good"},
        headers=auth_headers(test_admin),
    )

    db_session.refresh(job)
    assert response.status_code == 200
    assert response.json()["status"] == "active"
    assert job.status_history[-1]["to"] == "active"


def test_admin_bulk_set_status_returns_requested_and_updated_counts(
    client, test_admin, auth_headers, sample_job, db_session
):
    jobs = [sample_job(status="pending") for _ in range(3)]

    response = client.patch(
        "/admin/jobs/bulk-status",
        json={"job_ids": [job.id for job in jobs], "status": "flagged", "reason": "Bulk moderation"},
        headers=auth_headers(test_admin),
    )

    assert response.status_code == 200
    assert response.json() == {"requested": 3, "updated": 3}
    for job in jobs:
        db_session.refresh(job)
        assert job.status == "flagged"


def test_bulk_status_more_than_200_items_is_rejected(client, test_admin, auth_headers):
    response = client.patch(
        "/admin/jobs/bulk-status",
        json={"job_ids": [str(index) for index in range(201)], "status": "active"},
        headers=auth_headers(test_admin),
    )

    assert response.status_code == 422


def test_admin_grant_role_returns_updated_user(client, test_admin, test_user, auth_headers):
    response = client.post(f"/admin/users/{test_user.id}/roles/admin", headers=auth_headers(test_admin))

    assert response.status_code == 200
    assert "admin" in response.json()["roles"]


def test_admin_revoke_own_role_is_blocked(client, test_admin, auth_headers):
    response = client.delete(f"/admin/users/{test_admin.id}/roles/admin", headers=auth_headers(test_admin))

    assert response.status_code == 400


def test_admin_list_reports_returns_reports(client, test_admin, auth_headers, report_factory, sample_job, test_user):
    report_factory(job=sample_job(user=test_user), reporter=test_user)

    response = client.get("/admin/reports", headers=auth_headers(test_admin))

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_admin_can_resolve_report(client, test_admin, test_user, auth_headers, report_factory, sample_job):
    report = report_factory(job=sample_job(user=test_user), reporter=test_user)

    response = client.patch(
        f"/reports/{report.id}/resolve",
        json={"resolution": "reviewed"},
        headers=auth_headers(test_admin),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["resolution"] == "reviewed"
    assert body["resolved_by"] == test_admin.id


def test_report_serializer_wraps_uuid_fields_as_strings():
    """EMP-026a regression: the Postgres JobReport model maps id/job_id/
    reporter_user_id/resolved_by as uuid.UUID; ReportRead declares str.
    Serialization must coerce, or GET /admin/reports 500s."""
    from types import SimpleNamespace
    from uuid import uuid4

    from app.routers.reports import report_to_read

    report_id, job_id, reporter_id, resolver_id = uuid4(), uuid4(), uuid4(), uuid4()
    item = SimpleNamespace(
        id=report_id,
        job_id=job_id,
        reason="spam",
        details="Looks suspicious",
        reporter_user_id=reporter_id,
        resolution="pending",
        resolved_by=resolver_id,
        resolved_at=None,
        created_at=None,
    )

    read = report_to_read(item)

    assert read.id == str(report_id)
    assert read.job_id == str(job_id)
    assert read.reporter_user_id == str(reporter_id)
    assert read.resolved_by == str(resolver_id)
    assert read.reason == "spam"
