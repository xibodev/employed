from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.middleware.rate_limit import _client_ip, _hit, _is_trusted_proxy


def _request(peer_host: str | None, forwarded: str | None = None):
    headers = {}
    if forwarded is not None:
        headers["x-forwarded-for"] = forwarded
    return SimpleNamespace(
        client=SimpleNamespace(host=peer_host) if peer_host else None,
        headers=headers,
    )


def test_xff_ignored_when_peer_is_untrusted():
    """EMP-007 regression: a client connecting directly must not be able to
    rotate rate-limit buckets by sending X-Forwarded-For."""
    request = _request("203.0.113.9", forwarded="1.2.3.4")

    assert _client_ip(request) == "203.0.113.9"


def test_xff_rightmost_value_used_when_peer_is_trusted():
    # Rightmost value is the one appended by our own proxy; client-supplied
    # prefixes are spoofable.
    request = _request("127.0.0.1", forwarded="6.6.6.6, 198.51.100.7")

    assert _client_ip(request) == "198.51.100.7"


def test_private_range_peer_is_trusted_by_default():
    request = _request("172.18.0.2", forwarded="198.51.100.7")

    assert _client_ip(request) == "198.51.100.7"


def test_custom_trusted_proxy_list_overrides_default(monkeypatch):
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "trusted_proxy_ips", "192.0.2.10/32")

    assert _is_trusted_proxy("192.0.2.10") is True
    assert _is_trusted_proxy("127.0.0.1") is False


def test_non_ip_peer_is_never_trusted():
    # Starlette's TestClient reports peer host "testclient"
    assert _is_trusted_proxy("testclient") is False
    assert _is_trusted_proxy(None) is False


class FakeRedis:
    """Minimal shared-store stand-in proving cross-process semantics."""

    def __init__(self) -> None:
        self.store: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    def incr(self, key: str) -> int:
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    def expire(self, key: str, ttl: int) -> None:
        self.ttls[key] = ttl

    def close(self) -> None:  # pragma: no cover - interface parity
        pass


def test_redis_backed_rate_limit_shared_across_workers(monkeypatch):
    """EMP-007: with Redis configured the buckets are shared, so limits hold
    across workers (each call here simulates a different process)."""
    shared = FakeRedis()
    monkeypatch.setattr("app.middleware.rate_limit.redis_client", lambda: shared)

    for _ in range(3):
        _hit("scope:1.2.3.4", limit=3, window_seconds=60)

    with pytest.raises(HTTPException) as exc_info:
        _hit("scope:1.2.3.4", limit=3, window_seconds=60)

    assert exc_info.value.status_code == 429
    assert shared.ttls  # expiry was set on first hit


def test_in_memory_fallback_still_enforces_limit(monkeypatch):
    monkeypatch.setattr("app.middleware.rate_limit.redis_client", lambda: None)

    for _ in range(2):
        _hit("fallback:9.9.9.9", limit=2, window_seconds=60)

    with pytest.raises(HTTPException) as exc_info:
        _hit("fallback:9.9.9.9", limit=2, window_seconds=60)

    assert exc_info.value.status_code == 429
