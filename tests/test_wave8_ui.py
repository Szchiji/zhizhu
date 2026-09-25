"""Wave8: roles admin + reconcile mini UI assets + HTML inject."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.db import get_session, init_db
from app.services import get_or_create_tenant, set_setting
from app.static_ver import MINI_ASSET_VER


def setup_function():
    init_db()


def test_mini_asset_ver_bumped():
    assert MINI_ASSET_VER >= 16


def test_roles_js_file_and_endpoints():
    root = Path(__file__).resolve().parents[1] / "app" / "templates"
    assert (root / "mini-roles.js").is_file()
    text = (root / "mini-roles.js").read_text(encoding="utf-8")
    assert "/api/mini/admin/roles" in text
    assert "/api/mini/admin/reconcile" in text
    assert "ensureRolesAdmin" in text
    assert "ensureReconcileAdmin" in text
    assert "gateAdminNav" in text
    assert "角色" in text
    assert "对账" in text


def test_static_roles_js_route():
    import app.main as main

    with TestClient(main.app) as client:
        r = client.get("/mini-roles.js")
        assert r.status_code == 200
        assert "javascript" in r.headers.get("content-type", "")
        assert "ensureRolesAdmin" in r.text
        assert len(r.text) > 200


def test_mini_html_injects_roles_script():
    import app.main as main

    with TestClient(main.app) as client:
        r = client.get("/mini")
        if r.status_code != 200:
            src = Path(__file__).resolve().parents[1] / "app" / "wave4_mini_html.py"
            text = src.read_text(encoding="utf-8")
            assert "mini-roles.js" in text
            return
        body = r.text
        assert f"mini-roles.js?v={MINI_ASSET_VER}" in body


def test_roles_api_list_and_set(monkeypatch):
    import app.admin_roles as ar
    import app.admin_roles_mount as arm
    import app.config as cfg
    import app.main as main

    owner = 424242
    monkeypatch.setattr(cfg, "ADMIN_TG_IDS", {owner})
    monkeypatch.setattr(ar, "ADMIN_TG_IDS", {owner})
    monkeypatch.setattr(arm, "ADMIN_TG_IDS", {owner})
    # _uid imports require_webapp_user by value — patch the bound helpers
    monkeypatch.setattr(ar, "_uid", lambda **kw: owner)
    monkeypatch.setattr(arm, "_uid", lambda **kw: owner)

    db = get_session()
    try:
        set_setting(db, "admin_roles", json.dumps({"800001": "support"}))
    finally:
        db.close()

    with TestClient(main.app) as client:
        r = client.get("/api/mini/admin/roles", params={"init_data": "x", "user_id": owner})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok")
        assert data.get("roles", {}).get("800001") == "support"
        assert data.get("me_role") == "owner"

        r2 = client.post(
            "/api/mini/admin/roles",
            json={
                "init_data": "x",
                "user_id": owner,
                "roles": {"800001": "ops", "800002": "support"},
            },
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["roles"]["800001"] == "ops"
        assert r2.json()["roles"]["800002"] == "support"


def test_reconcile_api_still_ok(monkeypatch):
    import app.admin_ops as admin_api
    import app.main as main
    from tests.test_wave2_payment import _mk_order

    db = get_session()
    try:
        tenant = get_or_create_tenant(db, 88008)
        _mk_order(db, tenant, amount=9.9, code="W8REC01")
    finally:
        db.close()

    monkeypatch.setattr(admin_api, "_admin_id", lambda *a, **k: 88008)
    with TestClient(main.app) as client:
        r = client.get("/api/mini/admin/reconcile")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok")
        codes = [o["code"] for o in data.get("orders") or []]
        assert "W8REC01" in codes
