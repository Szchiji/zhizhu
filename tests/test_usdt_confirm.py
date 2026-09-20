"""USDT confirm: secret fail-closed + in-memory rate limit (no network)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.rate_limit import SlidingWindowLimiter


def test_sliding_window_limiter_blocks_after_limit():
    lim = SlidingWindowLimiter()
    assert lim.allow("k", limit=2, window_sec=60) is True
    assert lim.allow("k", limit=2, window_sec=60) is True
    assert lim.allow("k", limit=2, window_sec=60) is False
    lim.clear()
    assert lim.allow("k", limit=2, window_sec=60) is True


def test_usdt_confirm_secret_not_configured_fail_closed(monkeypatch):
    import app.main as main

    monkeypatch.setattr(main, "USDT_CONFIRM_SECRET", "")
    main._usdt_confirm_limiter.clear()
    with TestClient(main.app) as client:
        r = client.post("/api/usdt/confirm", json={"code": "ABCD", "secret": "x"})
    assert r.status_code == 503
    assert "secret" in str(r.json().get("detail", "")).lower()


def test_usdt_confirm_bad_secret_forbidden(monkeypatch):
    import app.main as main

    monkeypatch.setattr(main, "USDT_CONFIRM_SECRET", "expected-secret")
    main._usdt_confirm_limiter.clear()
    with TestClient(main.app) as client:
        r = client.post("/api/usdt/confirm", json={"code": "ABCD", "secret": "wrong"})
    assert r.status_code == 403


def test_usdt_confirm_rate_limited(monkeypatch):
    import app.main as main

    monkeypatch.setattr(main, "USDT_CONFIRM_SECRET", "expected-secret")
    monkeypatch.setattr(main, "USDT_CONFIRM_IP_LIMIT", 2)
    monkeypatch.setattr(main, "USDT_CONFIRM_IP_WINDOW", 60)
    main._usdt_confirm_limiter.clear()
    with TestClient(main.app) as client:
        assert client.post("/api/usdt/confirm", json={"code": "X", "secret": "no"}).status_code == 403
        assert client.post("/api/usdt/confirm", json={"code": "X", "secret": "no"}).status_code == 403
        r = client.post("/api/usdt/confirm", json={"code": "X", "secret": "no"})
    assert r.status_code == 429
