from __future__ import annotations

from datetime import timedelta

from app.services.market import MARKETS
from app.services.model_utils import utcnow


def test_public_jobs_strips_contact_field(client, sample_job, sample_market_headers):
    sample_job()

    response = client.get("/api/jobs", headers=sample_market_headers("mz"))

    assert response.status_code == 200
    assert response.json()["items"][0]["contact"] is None


def test_public_featured_jobs_returns_only_featured_jobs(client, job_factory, sample_market_headers):
    featured = job_factory(title="Featured API Job", featured=True)
    job_factory(title="Regular API Job", featured=False)

    response = client.get("/api/featuredJobs", headers=sample_market_headers("mz"))

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [featured.id]
    assert response.json()[0]["contact"] is None


def test_public_jobs_supports_page_and_page_size(client, job_factory, sample_market_headers):
    for index in range(5):
        job_factory(title=f"Public Role {index}")

    response = client.get("/api/jobs?page=2&page_size=2", headers=sample_market_headers("mz"))

    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 2
    assert body["page_size"] == 2
    assert len(body["items"]) == 2


def test_public_jobs_include_site_url_and_rate_limit(client, sample_job, sample_market_headers):
    sample_job(title="Rate Limited Job")
    headers = sample_market_headers("mz")

    first = client.get("/api/jobs", headers=headers)
    for _ in range(59):
        client.get("/api/jobs", headers=headers)
    limited = client.get("/api/jobs", headers=headers)

    assert first.status_code == 200
    assert first.json()["items"][0]["site_url"].endswith("/rate-limited-job")
    assert limited.status_code == 429


def test_public_jobs_pushes_pagination_and_count_to_sql(client, job_factory, sample_market_headers, db_session):
    """CARTO-001 regression: /api/jobs (the alias the frontend calls) must
    LIMIT/OFFSET and COUNT in SQL instead of materializing every active row
    in Python, exactly like /jobs after EMP-010."""
    from sqlalchemy import event

    for index in range(5):
        job_factory(title=f"Alias Engineer {index}")

    statements: list[str] = []
    engine = db_session.get_bind()

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        response = client.get("/api/jobs?page=1&page_size=2", headers=sample_market_headers("mz"))
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 5
    assert len(payload["items"]) == 2
    joined = " ".join(s.lower() for s in statements)
    assert "limit" in joined, f"no LIMIT pushed down: {statements}"
    assert "count" in joined, f"no COUNT pushed down: {statements}"


def test_public_jobs_parity_market_active_window_and_order(client, job_factory, sample_market_headers):
    """CARTO-001 parity: SQL path must reproduce the old Python filtering —
    active-only, market-scoped, 90-day window, newest-first, contact omitted."""
    job_factory(title="Newest Role", created_at=utcnow() - timedelta(days=1))
    job_factory(title="Oldest Role", created_at=utcnow() - timedelta(days=10))
    job_factory(title="Pending Role", status="pending")
    job_factory(title="Inactive Role", status="inactive")
    job_factory(title="Stale Role", created_at=utcnow() - timedelta(days=91))
    job_factory(title="Mexico Role", country=MARKETS["mx"]["country"])

    mz = client.get("/api/jobs", headers=sample_market_headers("mz"))
    mx = client.get("/api/jobs", headers=sample_market_headers("mx"))

    assert mz.status_code == 200
    payload = mz.json()
    assert [item["title"] for item in payload["items"]] == ["Newest Role", "Oldest Role"]
    assert payload["total"] == 2
    assert all(item["contact"] is None for item in payload["items"])
    assert [item["title"] for item in mx.json()["items"]] == ["Mexico Role"]


def test_public_jobs_query_filters_match_python_behavior(client, job_factory, sample_market_headers):
    """CARTO-001 parity: search/jobtype/remote filters behave exactly as the
    old in-Python filtering did, including the invalid-jobtype empty result."""
    job_factory(title="Backend Engineer", company="Acme")
    job_factory(title="Designer", company="Beta Studio")
    job_factory(title="Marketer", company="Acme", job_type="Part Time")
    job_factory(title="Remote QA", company="Gamma", remote=True)

    by_text = client.get("/api/jobs?query=acme", headers=sample_market_headers("mz"))
    by_type = client.get("/api/jobs?jobtype=Part Time", headers=sample_market_headers("mz"))
    by_remote = client.get("/api/jobs?remote=true", headers=sample_market_headers("mz"))
    invalid_type = client.get("/api/jobs?jobtype=Bogus", headers=sample_market_headers("mz"))

    assert {item["title"] for item in by_text.json()["items"]} == {"Backend Engineer", "Marketer"}
    assert [item["title"] for item in by_type.json()["items"]] == ["Marketer"]
    assert [item["title"] for item in by_remote.json()["items"]] == ["Remote QA"]
    assert invalid_type.json()["total"] == 0


def test_public_featured_jobs_parity_window_order_and_cap(client, job_factory, sample_market_headers, db_session):
    """CARTO-001 parity: /api/featuredJobs keeps its deterministic contract —
    active + in-market + featured_through >= now, newest-first, capped at 3 —
    while pushing the work into SQL (LIMIT visible in the statements)."""
    from sqlalchemy import event

    now = utcnow()
    job_factory(title="Featured Old", featured=True, created_at=now - timedelta(days=3))
    job_factory(title="Featured New", featured=True, created_at=now - timedelta(days=1))
    job_factory(title="Featured Mid", featured=True, created_at=now - timedelta(days=2))
    job_factory(title="Featured Extra", featured=True, created_at=now - timedelta(days=4))
    expired = job_factory(title="Featured Expired", featured=True, created_at=now - timedelta(days=5))
    expired.featured_through = now - timedelta(days=1)
    db_session.commit()
    job_factory(title="Featured Pending", featured=True, status="pending")
    job_factory(title="Featured MX", featured=True, country=MARKETS["mx"]["country"])

    statements: list[str] = []
    engine = db_session.get_bind()

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        response = client.get("/api/featuredJobs", headers=sample_market_headers("mz"))
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert response.status_code == 200
    titles = [item["title"] for item in response.json()]
    assert titles == ["Featured New", "Featured Mid", "Featured Old"]
    assert all(item["contact"] is None for item in response.json())
    joined = " ".join(s.lower() for s in statements)
    assert "limit" in joined, f"no LIMIT pushed down: {statements}"
