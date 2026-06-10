from __future__ import annotations


def test_mz_host_resolves_to_mz_market(client):
    response = client.get("/health", headers={"Host": "mz.employed.co.mz"})

    assert response.status_code == 200
    assert response.headers["x-market"] == "mz"


def test_mx_host_resolves_to_mx_market(client):
    response = client.get("/health", headers={"Host": "mx.employed.co.mz"})

    assert response.status_code == 200
    assert response.headers["x-market"] == "mx"


def test_unknown_host_defaults_to_mz_market(client):
    response = client.get("/health", headers={"Host": "unknown.employed.co.mz"})

    assert response.status_code == 200
    assert response.headers["x-market"] == "mz"


def test_localhost_defaults_to_mz_market(client):
    response = client.get("/health", headers={"Host": "localhost:3000"})

    assert response.status_code == 200
    assert response.headers["x-market"] == "mz"


def test_x_forwarded_host_takes_precedence_over_host(client):
    """EMP-001 regression: the frontend sends X-Forwarded-Host with the
    market hostname; the Host header carries the API hostname in any
    split-host topology and must not win."""
    response = client.get(
        "/health",
        headers={"Host": "api.employed.example", "X-Forwarded-Host": "mx.employed.example"},
    )

    assert response.status_code == 200
    assert response.headers["x-market"] == "mx"


def test_x_forwarded_host_first_value_wins_in_chain(client):
    response = client.get(
        "/health",
        headers={"Host": "api.employed.example", "X-Forwarded-Host": "mx.employed.example, proxy.internal"},
    )

    assert response.status_code == 200
    assert response.headers["x-market"] == "mx"


def test_x_forwarded_host_scopes_job_listings_to_market(client, job_factory):
    from app.services.market import MARKETS

    job_factory(title="MZ Role", country=MARKETS["mz"]["country"])
    job_factory(title="MX Role", country=MARKETS["mx"]["country"])

    response = client.get(
        "/jobs",
        headers={"Host": "api.employed.example", "X-Forwarded-Host": "mx.employed.example:3300"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["title"] for item in payload["items"]] == ["MX Role"]
    assert response.headers["x-market"] == "mx"


def test_empty_x_forwarded_host_falls_back_to_host(client):
    response = client.get("/health", headers={"Host": "mx.employed.co.mz", "X-Forwarded-Host": ""})

    assert response.status_code == 200
    assert response.headers["x-market"] == "mx"
