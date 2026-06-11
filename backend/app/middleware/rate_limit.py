"""Request rate limiting (EMP-007).

Primary store: Redis fixed-window counters (`ratelimit:<scope>:<ip>`), shared
across workers/replicas. Fallback: the original in-process sliding-window
limiter for environments without REDIS_URL (dev/tests).

Client IP derivation: X-Forwarded-For is only honored when the directly
connected peer is a trusted proxy (TRUSTED_PROXY_IPS, defaults to loopback +
RFC1918), and then the RIGHTMOST value is used — the one appended by our own
proxy — because any client-supplied prefix is spoofable.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import threading
import time
from collections import defaultdict, deque
from typing import Any

from fastapi import HTTPException, Request, status

from app.config import settings

logger = logging.getLogger(__name__)

# Loopback + RFC1918/docker-bridge ranges: covers the supported topology of a
# reverse proxy (Caddy) on the same box / compose network. Override with
# TRUSTED_PROXY_IPS (comma-separated IPs or CIDRs) for anything else.
DEFAULT_TRUSTED_PROXIES = "127.0.0.1/32,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"

RATE_LIMIT_KEY_PREFIX = "ratelimit:"


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, *, limit: int, window_seconds: int) -> None:
        now = time.time()
        cutoff = now - window_seconds
        with self._lock:
            bucket = self._buckets[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded. Try again in {window_seconds} seconds.",
                )
            bucket.append(now)


rate_limiter = InMemoryRateLimiter()


def redis_client() -> Any | None:
    """Short-lived Redis client, or None when Redis is not configured/usable."""
    url = getattr(settings, "redis_url", None)
    if not url:
        return None
    try:
        from redis import Redis

        return Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
    except Exception:  # noqa: BLE001 — redis is optional infra
        logger.warning("rate_limit.redis_unavailable", exc_info=True)
        return None


def close_quietly(client: Any) -> None:
    close = getattr(client, "close", None)
    if callable(close):
        try:
            close()
        except Exception:  # noqa: BLE001
            pass


def _trusted_proxy_networks() -> list[Any]:
    raw = getattr(settings, "trusted_proxy_ips", None) or os.getenv("TRUSTED_PROXY_IPS") or DEFAULT_TRUSTED_PROXIES
    networks: list[Any] = []
    for part in str(raw).split(","):
        entry = part.strip()
        if not entry:
            continue
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            logger.warning("rate_limit.invalid_trusted_proxy entry=%s", entry)
    return networks


def _is_trusted_proxy(host: str | None) -> bool:
    if not host:
        return False
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(addr in network for network in _trusted_proxy_networks())


def _client_ip(request: Request) -> str:
    direct = request.client.host if request.client else None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded and _is_trusted_proxy(direct):
        candidate = forwarded.split(",")[-1].strip()
        if candidate:
            return candidate
    return direct or "unknown"


def _hit(key: str, *, limit: int, window_seconds: int) -> None:
    """Count a hit against Redis when available, else the in-process buckets."""
    client = redis_client()
    if client is not None:
        count: int | None = None
        try:
            name = f"{RATE_LIMIT_KEY_PREFIX}{key}"
            count = int(client.incr(name))
            if count == 1:
                client.expire(name, window_seconds)
        except Exception:  # noqa: BLE001 — never let infra failures 500 a request
            logger.warning("rate_limit.redis_hit_failed key=%s", key, exc_info=True)
            count = None
        finally:
            close_quietly(client)
        if count is not None:
            if count > limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded. Try again in {window_seconds} seconds.",
                )
            return
    rate_limiter.hit(key, limit=limit, window_seconds=window_seconds)


def rate_limit(limit: int, window_seconds: int, scope: str):
    async def dependency(request: Request) -> None:
        key = f"{scope}:{_client_ip(request)}"
        _hit(key, limit=limit, window_seconds=window_seconds)

    return dependency
