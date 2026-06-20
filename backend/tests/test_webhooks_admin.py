from __future__ import annotations

from uuid import uuid4


def test_register_webhook_endpoint_requires_authentication(client):
    """The outbound webhook-endpoint admin router is mounted distinctly from the
    inbound ``/webhooks`` provider package and must reject unauthenticated
    callers before any work is done (R20.4)."""
    response = client.post(
        "/webhook-endpoints",
        json={
            "url": "https://example.com/hook",
            "secret": "s3cret",
            "events": ["job.published"],
        },
    )

    assert response.status_code == 401


def test_list_webhook_endpoints_requires_authentication(client):
    response = client.get("/webhook-endpoints")

    assert response.status_code == 401


def test_deactivate_webhook_endpoint_requires_authentication(client):
    response = client.delete(f"/webhook-endpoints/{uuid4()}")

    assert response.status_code == 401


def test_webhook_admin_routes_are_distinct_from_inbound_webhooks():
    """The OUTBOUND admin router lives under ``/webhook-endpoints`` so it never
    collides with the inbound provider webhooks mounted at ``/webhooks``."""
    from app.main import app

    paths = {route.path for route in app.routes if hasattr(route, "path")}

    assert "/webhook-endpoints" in paths
    assert "/webhook-endpoints/{endpoint_id}" in paths
    assert not any(path.startswith("/webhooks/webhook-endpoints") for path in paths)
