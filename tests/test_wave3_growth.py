"""Wave 3: coupons, public plans, clone webhook."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.coupons import Coupon, redeem_coupon
from app.db import get_session, init_db
from app.services import get_or_create_tenant


def setup_function():
    init_db()


def test_public_plans_endpoint():
    import app.main as main

    with TestClient(main.app) as client:
        r = client.get("/api/mini/plans")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok")
        assert isinstance(data.get("plans"), list)
        assert data["plans"]


def test_coupon_redeem_grants_days(monkeypatch):
    import app.coupons as coupons_mod
    import app.main as main

    db = get_session()
    try:
        db.add(Coupon(code="WAVE3FREE7", kind="days", value_days=7, max_redemptions=10))
        db.commit()
        tenant = get_or_create_tenant(db, 300001)
        ok, msg, days = redeem_coupon(db, tenant_id=tenant.id, tg_id=300001, code="WAVE3FREE7")
        assert ok, msg
        assert days == 7
        db.commit()
        db.refresh(tenant)
        assert tenant.paid_until is not None
    finally:
        db.close()

    monkeypatch.setattr(coupons_mod, "_admin", lambda *a, **k: 42)
    with TestClient(main.app) as client:
        r = client.get("/api/mini/admin/coupons", params={"user_id": 42, "init_data": "x"})
        assert r.status_code == 200, r.text
        codes = {c["code"] for c in r.json().get("coupons", [])}
        assert "WAVE3FREE7" in codes


def test_clone_webhook_snippet_present():
    from pathlib import Path

    text = Path("app/_pb_c11.txt").read_text(encoding="utf-8")
    assert "setWebhook" in text
    assert "/wh/t/" in text
