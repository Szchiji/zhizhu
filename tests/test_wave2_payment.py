"""Wave 2: USDT exclusive claim, revoke, reconcile, pending me payload."""
from __future__ import annotations

import asyncio
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_session, init_db
from app.models import Order, utcnow
from app.services import activate_order, get_or_create_tenant, new_code, set_setting
from app.wave2_revoke import revoke_order


def setup_function():
    init_db()


def _mk_order(db, tenant, *, amount, status="pending", code=None, rail="usdt"):
    order = Order(
        public_code=code or new_code(),
        tenant_id=tenant.id,
        rail=rail,
        plan="year",
        period_days=365,
        amount=amount,
        currency="USDT" if rail == "usdt" else "XTR",
        chain="trc20" if rail == "usdt" else None,
        pay_address="TTESTADDR",
        status=status,
        expires_at=utcnow() + timedelta(minutes=20),
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def test_usdt_exclusive_claim_same_amount(monkeypatch):
    """Two pending orders with same amount: only one claims the matching tx."""
    import app.usdt_watch as uw

    db = get_session()
    try:
        t1 = get_or_create_tenant(db, 900001)
        t2 = get_or_create_tenant(db, 900002)
        o1 = _mk_order(db, t1, amount=99.01, code="W2A001")
        o2 = _mk_order(db, t2, amount=99.01, code="W2A002")
        assert float(o1.amount) == float(o2.amount)
        set_setting(db, "usdt_address", "TTESTADDR")

        txid = "tx_wave2_exclusive_1"
        fake_txs = [
            {
                "transaction_id": txid,
                "to": "TTESTADDR",
                "value": str(int(round(99.01 * 1_000_000))),
                "block_timestamp": int((__import__("time").time()) * 1000),
            }
        ]

        async def _fake_incoming(addr):
            return fake_txs

        monkeypatch.setattr(uw, "_incoming", _fake_incoming)
        n = asyncio.run(uw.check_once(bot=None))
        assert n == 1
        db.expire_all()
        rows = list(db.scalars(select(Order).where(Order.public_code.in_(["W2A001", "W2A002"]))))
        active = [r for r in rows if r.status == "active"]
        open_rows = [r for r in rows if r.status in {"pending", "confirming", "draft"}]
        assert len(active) == 1
        assert active[0].txid == txid
        assert len(open_rows) == 1
        assert not open_rows[0].txid
    finally:
        db.close()


def test_revoke_order_pulls_back_days():
    db = get_session()
    try:
        tenant = get_or_create_tenant(db, 900010)
        order = _mk_order(db, tenant, amount=50, status="pending", code="W2REV1", rail="stars")
        order.telegram_charge_id = "chg_wave2_1"
        activate_order(db, order)
        db.commit()
        db.refresh(tenant)
        assert tenant.paid_until is not None
        before = tenant.paid_until
        revoke_order(db, order, reason="test_revoke")
        db.commit()
        db.refresh(tenant)
        db.refresh(order)
        assert order.status == "refunded"
        if tenant.paid_until:
            assert tenant.paid_until < before
    finally:
        db.close()


def test_reconcile_and_revoke_admin_endpoints(monkeypatch):
    import app.admin_ops as admin_api
    import app.main as main

    db = get_session()
    try:
        tenant = get_or_create_tenant(db, 42)
        order = _mk_order(db, tenant, amount=12.34, code="W2REC1")
        order.expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()

    monkeypatch.setattr(admin_api, "_admin_id", lambda *a, **k: 42)
    with TestClient(main.app) as client:
        r = client.get("/api/mini/admin/reconcile")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok")
        codes = {o["code"] for o in data.get("orders", [])}
        assert "W2REC1" in codes
        flagged = [o for o in data["orders"] if o["code"] == "W2REC1"][0]
        assert flagged.get("flag") == "expired_unpaid"

        db = get_session()
        try:
            order = db.scalar(select(Order).where(Order.public_code == "W2REC1"))
            activate_order(db, order)
            db.commit()
        finally:
            db.close()

        r2 = client.post("/api/mini/admin/revoke", json={"code": "W2REC1"})
        assert r2.status_code == 200, r2.text
        assert r2.json().get("ok")


def test_mini_me_includes_pending(monkeypatch):
    import app.main as main
    import app.tg_webapp as tw

    db = get_session()
    try:
        tenant = get_or_create_tenant(db, 77)
        _mk_order(db, tenant, amount=88.88, code="W2PEND1")
    finally:
        db.close()

    monkeypatch.setattr(tw, "require_webapp_user", lambda **kw: 77)
    monkeypatch.setattr(main, "require_webapp_user", lambda **kw: 77, raising=False)
    if hasattr(main, "_uid"):
        monkeypatch.setattr(main, "_uid", lambda *a, **k: 77)

    with TestClient(main.app) as client:
        r = client.get("/api/mini/me", params={"init_data": "x", "user_id": 77})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("pending"), data
        assert data["pending"]["code"] == "W2PEND1"
        assert "88.88" in str(data["pending"]["amount"])
        assert data["pending"].get("expires_at")
