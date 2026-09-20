"""Redis sliding-window limiter tests (no real Redis server)."""
from __future__ import annotations

import sys
import types

from app.rate_limit import RedisSlidingWindowLimiter, SlidingWindowLimiter, get_limiter


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, dict[str, float]] = {}

    def ping(self) -> bool:
        return True

    def pipeline(self):
        return _FakePipe(self)

    def scan(self, cursor=0, match="*", count=200):
        import fnmatch

        keys = [k for k in self.store if fnmatch.fnmatch(k, match)]
        return 0, keys

    def delete(self, *keys):
        for k in keys:
            self.store.pop(k, None)
        return len(keys)


class _FakePipe:
    def __init__(self, r: _FakeRedis) -> None:
        self.r = r
        self.ops: list = []

    def zremrangebyscore(self, key, min_s, max_s):
        self.ops.append(("zrem", key, min_s, max_s))
        return self

    def zcard(self, key):
        self.ops.append(("zcard", key))
        return self

    def zadd(self, key, mapping):
        self.ops.append(("zadd", key, mapping))
        return self

    def expire(self, key, sec):
        self.ops.append(("expire", key, sec))
        return self

    def execute(self):
        out = []
        for op in self.ops:
            if op[0] == "zrem":
                _, key, _min_s, max_s = op
                z = self.r.store.setdefault(key, {})
                for m, score in list(z.items()):
                    if score <= max_s:
                        del z[m]
                out.append(0)
            elif op[0] == "zcard":
                out.append(len(self.r.store.get(op[1], {})))
            elif op[0] == "zadd":
                _, key, mapping = op
                self.r.store.setdefault(key, {}).update(mapping)
                out.append(len(mapping))
            elif op[0] == "expire":
                out.append(1)
        self.ops.clear()
        return out


def _install_fake_redis(monkeypatch, client):
    mod = types.ModuleType("redis")

    class Redis:
        @staticmethod
        def from_url(url, decode_responses=True):
            return client

    mod.Redis = Redis
    monkeypatch.setitem(sys.modules, "redis", mod)


def test_redis_sliding_window_blocks_after_limit(monkeypatch):
    fake = _FakeRedis()
    _install_fake_redis(monkeypatch, fake)
    lim = RedisSlidingWindowLimiter("redis://localhost:6379/0")
    assert lim.allow("k", limit=2, window_sec=60) is True
    assert lim.allow("k", limit=2, window_sec=60) is True
    assert lim.allow("k", limit=2, window_sec=60) is False
    lim.clear()
    assert lim.allow("k", limit=2, window_sec=60) is True


def test_get_limiter_memory_without_redis_url(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    lim = get_limiter()
    assert isinstance(lim, SlidingWindowLimiter)


def test_get_limiter_falls_back_when_redis_dead(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")

    mod = types.ModuleType("redis")

    class Redis:
        @staticmethod
        def from_url(url, decode_responses=True):
            raise ConnectionError("no redis")

    mod.Redis = Redis
    monkeypatch.setitem(sys.modules, "redis", mod)
    lim = get_limiter()
    assert isinstance(lim, SlidingWindowLimiter)
