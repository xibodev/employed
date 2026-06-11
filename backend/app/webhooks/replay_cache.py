"""Webhook replay-protection cache (EMP-019).

Primary store: Redis keys ``replay:<namespace>:<event-key>`` with TTL, so
deduplication survives restarts and is shared across workers. Fallback: the
original in-process LRU/TTL map for environments without REDIS_URL. Never
raises into the webhook request path.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict

from app.middleware.rate_limit import close_quietly, redis_client

logger = logging.getLogger(__name__)


class ReplayCache:
    def __init__(self, ttl_seconds: int = 300, max_entries: int = 10000, namespace: str = "webhook"):
        self.ttl_seconds = max(ttl_seconds, 1)
        self.max_entries = max(max_entries, 1)
        self.namespace = namespace
        self._entries: OrderedDict[str, float] = OrderedDict()
        self._lock = threading.Lock()

    def _redis_key(self, key: str) -> str:
        return f"replay:{self.namespace}:{key}"

    def _prune(self, now: float) -> None:
        expiry = now - self.ttl_seconds
        while self._entries:
            key, seen_at = next(iter(self._entries.items()))
            if seen_at > expiry and len(self._entries) <= self.max_entries:
                break
            self._entries.popitem(last=False)

    def contains(self, key: str | None) -> bool:
        if not key:
            return False
        client = redis_client()
        if client is not None:
            try:
                return client.get(self._redis_key(key)) is not None
            except Exception:  # noqa: BLE001 — fall back to in-process store
                logger.warning("replay_cache.redis_read_failed namespace=%s", self.namespace, exc_info=True)
            finally:
                close_quietly(client)
        now = time.monotonic()
        with self._lock:
            self._prune(now)
            if key not in self._entries:
                return False
            self._entries.move_to_end(key)
            return True

    def add(self, key: str | None) -> None:
        if not key:
            return
        client = redis_client()
        if client is not None:
            try:
                client.set(self._redis_key(key), "1", ex=self.ttl_seconds)
                return
            except Exception:  # noqa: BLE001
                logger.warning("replay_cache.redis_write_failed namespace=%s", self.namespace, exc_info=True)
            finally:
                close_quietly(client)
        now = time.monotonic()
        with self._lock:
            self._entries[key] = now
            self._entries.move_to_end(key)
            self._prune(now)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
