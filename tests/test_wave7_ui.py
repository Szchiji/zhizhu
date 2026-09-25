"""Wave7: pending/ops mini UI assets + HTML inject + pending API still works."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.db import get_session, init_db
from app.services import get_or_create_tenant
from app.static_ver import MINI_ASSET_VER


def setup_function():
    init_db()


def test_mini_asset_ver_bumped():
    assert MINI_ASSET_VER >= 15


def test_pending_and_ops_files_exist():
    root = Path(__file__).resolve().parents[1] / "app" / "templates"
    assert (root / "mini-pending.js").is_file()
    assert (root / "mini-ops.js").is_file()
    pending = (root / "mini-pending.js").read_text(encoding="utf-8")
    ops = (root / "mini-ops.js").read_text(encoding="utf-8")
    assert "/api/mini/pending" in pending
    assert "restorePending" in pending
    assert "/api/mini/coupon/redeem" in ops
    assert "/api/mini/admin/coupons" in ops
    assert "/api/mini/admin/revoke" in ops


def test_static_js_routes():
    import app.main as main

    with TestClient(main.app) as client:
        for path in ("/mini-pending.js", "/mini-ops.js", "/mini-onboard.js", "/mini-confirm.js"):
            r = client.get(path)
            assert r.status_code == 200, path
            assert "javascript" in r.headers.get("content-type", "")
            assert len(r.text) > 50


def test_mini_html_injects_wave7_scripts(monkeypatch):
    import app.main as main

    # Some deployments gate /mini; hit middleware via ASGI if route exists.
    with TestClient(main.app) as client:
        r = client.get("/mini")
        if r.status_code != 200:
            # fallback: unit-check middleware source wiring
            src = Path(__file__).resolve().parents[1] / "app" / "wave4_mini_html.py"
            text = src.read_text(encoding="utf-8")
            assert "mini-pending.js" in text and "mini-ops.js" in text
            return
        body = r.text
        assert f"mini-pending.js?v={MINI_ASSET_VER}" in body
        assert f"mini-ops.js?v={MINI_ASSET_VER}" in body


def test_pending_api_still_ok(monkeypatch):
    import app.main as main
    import app.tg_webapp as tw
    from tests.test_wave2_payment import _mk_order

    db = get_session()
    try:
        tenant = get_or_create_tenant(db, 77007)
        _mk_order(db, tenant, amount=12.34, code="W7PEND1")
    finally:
        db.close()

    monkeypatch.setattr(tw, "require_webapp_user", lambda **kw: 77007)
    monkeypatch.setattr(main, "require_webapp_user", lambda **kw: 77007, raising=False)

    with TestClient(main.app) as client:
        r = client.get("/api/mini/pending", params={"init_data": "x", "user_id": 77007})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("pending"), data
        assert data["pending"]["code"] == "W7PEND1"
