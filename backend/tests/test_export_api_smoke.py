from __future__ import annotations

from uuid import uuid4


def test_export_routes_are_mounted_with_version_segment():
    """The read-only Export API is mounted on the app and every route carries
    the API version in its path (``/export/v1/...``) rather than a header or
    query parameter (R21.1, R21.3)."""
    from app.main import app

    paths = {route.path for route in app.routes if hasattr(route, "path")}

    assert "/export/v1/candidates/{identifier}" in paths
    assert "/export/v1/positions/{identifier}" in paths
    assert "/export/v1/jobs/{identifier}" in paths
    assert "/export/v1/applications/{identifier}" in paths


def test_export_route_paths_carry_v1_version_segment():
    """Each export route path includes the ``v1`` version segment, so the
    version is expressed in the URL path and bumping to ``/export/v2`` is a
    distinct namespace (R21.3)."""
    from app.main import app

    export_paths = [route.path for route in app.routes if hasattr(route, "path") and route.path.startswith("/export/")]

    assert export_paths, "expected at least one export route to be mounted"
    for path in export_paths:
        assert path.startswith("/export/v1/")


def test_export_route_rejects_unauthenticated_request():
    """The router is guarded by authentication at the router level, so an
    unauthenticated request to a mounted export route is rejected with 401,
    confirming the route is both mounted and protected (R21.1)."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.get(f"/export/v1/candidates/{uuid4()}")

    assert response.status_code == 401
