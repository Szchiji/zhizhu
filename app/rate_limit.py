"""Sliding-window rate limiter for USDT confirm.

Uses in-process memory by default. When ``REDIS_URL`` is set and reachable,
uses Redis so limits are shared across app replicas. If Redis is configured
but unavailable at startup, falls back to in-memory and logs a warning.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from collections import defaultdict, deque
from typing import Protocol

log = logging.getLogger("zhizhu.rate_limit")


class RateLimiter(Protocol):
    def allow(self, key: str, *, limit: int, window_sec: float) -> bool: ...

    def clear(self) -> None: ...


class SlidingWindowLimiter:
    """In-memory sliding window. Per-process only (not shared across replicas)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, *, limit: int, window_sec: float) -> bool:
        if limit <= 0:
            return True
        now = time.monotonic()
        window = max(0.1, float(window_sec))
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()


class RedisSlidingWindowLimiter:
    """Redis sorted-set sliding window; shared across replicas."""

    def __init__(self, url: str, *, prefix: str = "rl:usdt:") -> None:
        import redis

        self._r = redis.Redis.from_url(url, decode_responses=True)
        self._prefix = prefix
        self._r.ping()

    def allow(self, key: str, *, limit: int, window_sec: float) -> bool:
        if limit <= 0:
            return True
        now = time.time()
        window = max(0.1, float(window_sec))
        rk = f"{self._prefix}{key}"
        # Trim then check count atomically enough for rate limiting.
        pipe = self._r.pipeline()
        pipe.zremrangebyscore(rk, 0, now - window)
        pipe.zcard(rk)
        _trimmed, count = pipe.execute()
        if int(count) >= limit:
            return False
        member = f"{now:.6f}:{uuid.uuid4().hex[:12]}"
        pipe = self._r.pipeline()
        pipe.zadd(rk, {member: now})
        pipe.expire(rk, int(window) + 2)
        pipe.execute()
        return True

    def clear(self) -> None:
        cursor = 0
        pattern = f"{self._prefix}*"
        while True:
            cursor, keys = self._r.scan(cursor=cursor, match=pattern, count=200)
            if keys:
                self._r.delete(*keys)
            if cursor == 0:
                break


def get_limiter() -> RateLimiter:
    """Build the process limiter: Redis when REDIS_URL works, else memory."""
    url = (os.getenv("REDIS_URL") or "").strip()
    if not url:
        return SlidingWindowLimiter()
    try:
        lim = RedisSlidingWindowLimiter(url)
        log.info("USDT confirm rate limit: Redis (%s)", url.split("@")[-1])
        return lim
    except Exception as exc:  # noqa: BLE001 — fall back soft
        log.warning(
            "REDIS_URL set but Redis unavailable (%s); using in-memory rate limit",
            exc,
        )
        return SlidingWindowLimiter()
