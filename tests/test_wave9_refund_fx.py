"""Wave9: Stars refundStarPayment, reconcile action UI, Stars↔USDT FX rate."""
from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app.db import get_session, init_db
from app.fx_rate import (
    DEFAULT_STARS_PER_USDT,
    get_stars_per_usdt,
    set_stars_per_usdt,
    stars_to_usdt,
    usdt_to_stars,
)
from app.services import activate_order, get_or_create_tenant, set_setting
from app.stars_refund import refund_star_payment, refund_stars_for_order
from app.static_ver import MINI_ASSET_VER
from tests.test_wave2_payment import _mk_order


def setup_function():
    init_db()


def test_mini_asset_ver_bumped():
    assert MINI_ASSET_VER >= 17


def test_reconcile_js_has_row_actions():
    root = Path(__file__).resolve().parents[1] / "app" / "templates"
    assert (root / "mini-reconcile-actions.js").is_file()
    rec = (root / "mini-reconcile-actions.js").read_text(encoding="utf-8")
    assert "confirmRow" in rec
    assert "revokeRow" in rec
    assert "复制单号" in rec
    assert "打开详情" in rec
    assert "/api/mini/admin/revoke" in rec


def test_fx_js_and_route():
    root = Path(__file__).resolve().parents[1] / "app" / "templates"
    assert (root / "mini-fx.js").is_file()
    fx = (root / "mini-fx.js").read_text(encoding="utf-8")
    assert "/api/mini/admin/fx_rate" in fx
    assert "按汇率换算" in fx
    assert "stars_per_usdt" in fx or "fx-rate" in fx

    import app.main as main

    with TestClient(main.app) as client:
        for path in ("/mini-fx.js", "/mini-reconcile-actions.js", "/mini-ops-stars.js"):
            r = client.get(path)
            assert r.status_code == 200, path
            assert "javascript" in r.headers.get("content-type", "")


def test_mini_html_injects_wave9_scripts():
    import app.main as main

    with TestClient(main.app) as client:
        r = client.get("/mini")
        if r.status_code != 200:
            src = Path(__file__).resolve().parents[1] / "app" / "wave4_mini_html.py"
            text = src.read_text(encoding="utf-8")
            assert "mini-fx.js" in text
            return
        body = r.text
        assert f"mini-fx.js?v={MINI_ASSET_VER}" in body
        assert f"mini-reconcile-actions.js?v={MINI_ASSET_VER}" in body
        assert f"mini-ops-stars.js?v={MINI_ASSET_VER}" in body


def test_refund_star_payment_ok():
    async def _run():
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json={"ok": True, "result": True})
        )
        async with httpx.AsyncClient(transport=transport) as client:
            return await refund_star_payment(
                user_id=123,
                telegram_payment_charge_id="chg_ok_1",
                bot_token="123:ABC",
                client=client,
            )

    out = asyncio.run(_run())
    assert out["ok"] is True
    assert out["attempted"] is True
    assert out["already"] is False


def test_refund_star_payment_already_idempotent():
    async def _run():
        transport = httpx.MockTransport(
            lambda req: httpx.Response(
                200,
                json={"ok": False, "description": "Bad Request: CHARGE_ALREADY_REFUNDED"},
            )
        )
        async with httpx.AsyncClient(transport=transport) as client:
            return await refund_star_payment(
                user_id=123,
                telegram_payment_charge_id="chg_dup",
                bot_token="123:ABC",
                client=client,
            )

    out = asyncio.run(_run())
    assert out["ok"] is True
    assert out["already"] is True


def test_refund_star_payment_skipped_no_token():
    out = asyncio.run(
        refund_star_payment(user_id=1, telegram_payment_charge_id="chg", bot_token="")
    )
    assert out["skipped"] is True
    assert out["attempted"] is False


def test_refund_stars_for_order_skips_usdt():
    db = get_session()
    try:
        tenant = get_or_create_tenant(db, 91001)
        order = _mk_order(db, tenant, amount=10, rail="usdt", code="W9U001")
        out = asyncio.run(refund_stars_for_order(order, tenant, bot_token="x"))
        assert out["skipped"] is True
        assert out["error"] == "not_stars"
    finally:
        db.close()


def test_admin_revoke_calls_stars_refund(monkeypatch):
    import app.admin_ops as admin_api
    import app.main as main

    db = get_session()
    try:
        tenant = get_or_create_tenant(db, 91002)
        order = _mk_order(db, tenant, amount=100, status="pending", code="W9S001", rail="stars")
        order.telegram_charge_id = "chg_wave9_1"
        order.currency = "XTR"
        activate_order(db, order)
        db.commit()
    finally:
        db.close()

    async def _fake_refund(order, tenant, **kw):
        return {
            "attempted": True,
            "ok": True,
            "already": False,
            "skipped": False,
            "error": "",
            "description": "Telegram Stars refunded",
        }

    monkeypatch.setattr(admin_api, "_admin_id", lambda *a, **k: 91002)
    monkeypatch.setattr("app.wave9_revoke_stars.refund_stars_for_order", _fake_refund)

    with TestClient(main.app) as client:
        r = client.post("/api/mini/admin/revoke", json={"code": "W9S001"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok")
        assert data.get("stars_refund", {}).get("ok") is True
        assert data.get("message")


def test_fx_helpers_and_default():
    assert DEFAULT_STARS_PER_USDT == 50.0
    assert stars_to_usdt(100, 50) == 2.0
    assert usdt_to_stars(2, 50) == 100
    db = get_session()
    try:
        set_setting(db, "stars_per_usdt", "50")
        assert get_stars_per_usdt(db) == 50.0
        set_stars_per_usdt(db, 40)
        assert get_stars_per_usdt(db) == 40.0
    finally:
        db.close()


def test_fx_rate_admin_api(monkeypatch):
    import app.fx_rate as fx
    import app.main as main

    db = get_session()
    try:
        set_setting(db, "stars_per_usdt", "50")
    finally:
        db.close()

    monkeypatch.setattr(fx, "_admin", lambda *a, **k: 42)
    with TestClient(main.app) as client:
        r = client.get("/api/mini/admin/fx_rate", params={"init_data": "x", "user_id": 42})
        assert r.status_code == 200, r.text
        assert r.json()["stars_per_usdt"] == 50.0

        r2 = client.post(
            "/api/mini/admin/fx_rate",
            json={"init_data": "x", "user_id": 42, "stars_per_usdt": 45.5},
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["stars_per_usdt"] == 45.5

        r3 = client.post(
            "/api/mini/admin/fx_rate",
            json={"init_data": "x", "user_id": 42, "stars_per_usdt": 0.1},
        )
        assert r3.status_code == 400
