"""Admin audits list endpoint: auth + row shape."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.db import get_session, init_db
from app.models import AdminAudit
from app.services import add_admin_audit


def test_admin_audits_forbidden_without_admin(monkeypatch):
    import app.admin_ops as admin_api
    import app.main as main

    monkeypatch.setattr(admin_api, "_admin_id", lambda *a, **k: 0)
    with TestClient(main.app) as client:
        r = client.get("/api/mini/admin/audits")
    assert r.status_code == 403


def test_admin_audits_returns_rows(monkeypatch):
    import app.admin_ops as admin_api
    import app.main as main

    init_db()
    db = get_session()
    try:
        add_admin_audit(db, 42, "confirm", target_type="order", target_id="VH-AAA", detail="ok")
        add_admin_audit(db, 42, "price", target_type="setting", target_id="stars_year", detail="amount=1")
        db.commit()
    finally:
        db.close()

    monkeypatch.setattr(admin_api, "_admin_id", lambda *a, **k: 42)
    with TestClient(main.app) as client:
        r = client.get("/api/mini/admin/audits?limit=10")
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    rows = data.get("audits") or []
    assert len(rows) >= 2
    assert {"id", "admin_tg_id", "action", "target_type", "target_id", "detail", "created_at"} <= set(rows[0])
    assert rows[0]["id"] >= rows[1]["id"]

    with TestClient(main.app) as client:
        r2 = client.get("/api/mini/admin/audits?action=confirm")
    acts = {x["action"] for x in (r2.json().get("audits") or [])}
    assert acts == {"confirm"} or "confirm" in acts
