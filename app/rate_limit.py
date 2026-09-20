"""In-memory sliding-window rate limiter.

No Redis dependency: limits live in process memory and reset on restart.
With multiple app replicas each instance counts separately — use Redis later
if you need cluster-wide caps.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    """Allow at most `limit` hits per `window_sec` for each key."""

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
