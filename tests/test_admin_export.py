"""Admin CSV export: headers for orders/users; auth gate."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.db import get_session, init_db
from app.models import Order, Tenant
from app.services import get_or_create_tenant, new_code


def test_admin_export_forbidden(monkeypatch):
    import app.admin_ops as admin_api
    import app.main as main

    monkeypatch.setattr(admin_api, "_admin_id", lambda *a, **k: 0)
    with TestClient(main.app) as client:
        assert client.get("/api/mini/admin/export?kind=orders").status_code == 403
        assert client.get("/api/mini/admin/export?kind=users").status_code == 403


def test_admin_export_orders_header(monkeypatch):
    import app.admin_ops as admin_api
    import app.main as main

    init_db()
    db = get_session()
    try:
        tenant = get_or_create_tenant(db, 9001)
        db.add(
            Order(
                public_code=new_code(),
                tenant_id=tenant.id,
                rail="usdt",
                plan="year",
                period_days=365,
                amount=99,
                currency="USDT",
                status="pending",
            )
        )
        db.commit()
    finally:
        db.close()

    monkeypatch.setattr(admin_api, "_admin_id", lambda *a, **k: 42)
    with TestClient(main.app) as client:
        r = client.get("/api/mini/admin/export?kind=orders")
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
    text = r.content.decode("utf-8-sig")
    header = text.splitlines()[0]
    assert header == "code,rail,plan,amount,currency,status,tg_id,txid,paid_at,period_end,created_at"


def test_admin_export_users_header(monkeypatch):
    import app.admin_ops as admin_api
    import app.main as main

    init_db()
    db = get_session()
    try:
        get_or_create_tenant(db, 9002)
        db.commit()
    finally:
        db.close()

    monkeypatch.setattr(admin_api, "_admin_id", lambda *a, **k: 42)
    with TestClient(main.app) as client:
        r = client.get("/api/mini/admin/export?kind=users")
    assert r.status_code == 200
    text = r.content.decode("utf-8-sig")
    header = text.splitlines()[0]
    assert header == "tg_id,username,display_name,status,plan,paid_until,official_user_id"
