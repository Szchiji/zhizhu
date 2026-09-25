"""Wave10: clone instance list / enable-disable + white-label docs."""
from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app.crypto_token import encrypt_token
from app.db import get_session, init_db
from app.saas_clones import (
    is_clone_disabled,
    list_clone_instances,
    load_disabled_ids,
    save_disabled_ids,
)
from app.services import get_or_create_tenant, set_setting
from app.static_ver import MINI_ASSET_VER


def setup_function():
    init_db()


def test_mini_asset_ver_wave10():
    assert MINI_ASSET_VER >= 18


def test_white_label_doc_exists():
    doc = Path(__file__).resolve().parents[1] / "docs" / "WHITE_LABEL.md"
    assert doc.is_file()
    text = doc.read_text(encoding="utf-8")
    assert "setWebhook" in text
    assert "clone_disabled_ids" in text
    assert "\u7ecf\u9500\u5546" in text or "reseller" in text.lower()


def test_saas_js_served_and_injected():
    root = Path(__file__).resolve().parents[1]
    js = root / "app" / "templates" / "mini-saas.js"
    assert js.is_file()
    body = js.read_text(encoding="utf-8")
    assert "/api/mini/admin/clones" in body
    assert "\u514b\u9686\u5b9e\u4f8b" in body

    import app.main as main

    with TestClient(main.app) as client:
        r = client.get("/mini-saas.js")
        assert r.status_code == 200
        assert "javascript" in r.headers.get("content-type", "")

        r2 = client.get("/mini")
        if r2.status_code == 200:
            assert f"mini-saas.js?v={MINI_ASSET_VER}" in r2.text
        else:
            html = (root / "app" / "wave4_mini_html.py").read_text(encoding="utf-8")
            assert "mini-saas.js" in html


def test_disabled_ids_helpers():
    db = get_session()
    try:
        set_setting(db, "clone_disabled_ids", "[]")
        assert load_disabled_ids(db) == set()
        save_disabled_ids(db, {3, 1, 1})
        assert load_disabled_ids(db) == {1, 3}
        assert is_clone_disabled(db, 1)
        assert not is_clone_disabled(db, 2)
    finally:
        db.close()


def test_list_clone_instances_and_api(monkeypatch):
    import app.saas_clones as sc
    import app.main as main

    db = get_session()
    try:
        t = get_or_create_tenant(db, 10010)
        t.bot_id = 555001
        t.bot_username = "clone_bot_a"
        t.bot_token_enc = encrypt_token("123456:AAAtesttoken")
        t.status = "active"
        db.commit()
        tid = t.id
        items = list_clone_instances(db)
        assert any(x["tenant_id"] == tid and x["bot_username"] == "clone_bot_a" for x in items)
    finally:
        db.close()

    monkeypatch.setattr(sc, "_admin", lambda *a, **k: 42)

    async def _fake_del(token: str):
        return {"ok": True, "error": ""}

    async def _fake_set(token: str, tenant_id: int):
        return {"ok": True, "url": f"https://example.test/wh/t/{tenant_id}", "error": ""}

    async def _fake_info(token: str):
        return {"ok": True, "url": "https://example.test/wh/t/1", "pending_update_count": 0, "last_error_message": ""}

    monkeypatch.setattr(sc, "_tg_delete_webhook", _fake_del)
    monkeypatch.setattr(sc, "_tg_set_webhook", _fake_set)
    monkeypatch.setattr(sc, "_tg_webhook_info", _fake_info)

    with TestClient(main.app) as client:
        r = client.get("/api/mini/admin/clones", params={"user_id": 42, "init_data": "x"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok")
        assert data.get("count", 0) >= 1
        assert any(c["bot_username"] == "clone_bot_a" for c in data["clones"])

        r2 = client.post(
            "/api/mini/admin/clones",
            json={"init_data": "x", "user_id": 42, "action": "disable", "tenant_id": tid},
        )
        assert r2.status_code == 200, r2.text
        assert r2.json().get("clone_enabled") is False

        db = get_session()
        try:
            assert is_clone_disabled(db, tid)
        finally:
            db.close()

        r3 = client.post(
            "/api/mini/admin/clones",
            json={"init_data": "x", "user_id": 42, "action": "enable", "tenant_id": tid},
        )
        assert r3.status_code == 200, r3.text
        assert r3.json().get("clone_enabled") is True

        r4 = client.post(
            "/api/mini/admin/clones",
            json={"init_data": "x", "user_id": 42, "action": "webhook", "tenant_id": tid},
        )
        assert r4.status_code == 200, r4.text
        assert r4.json().get("webhook", {}).get("ok") is True


def test_handle_tenant_update_respects_disable(monkeypatch):
    from types import SimpleNamespace

    from app.tenant_bot import handle_tenant_update

    db = get_session()
    try:
        t = get_or_create_tenant(db, 10011)
        t.bot_username = "x"
        t.bot_token_enc = encrypt_token("1:x")
        save_disabled_ids(db, {t.id})
        db.commit()
        tenant_id = t.id
        tenant = db.get(type(t), tenant_id)
    finally:
        db.close()

    replied = {}

    class Msg:
        async def reply_text(self, text, **kw):
            replied["text"] = text

    update = SimpleNamespace(
        effective_message=Msg(),
        callback_query=None,
        inline_query=None,
    )

    asyncio.run(handle_tenant_update(update, tenant, bot=None))
    assert "\u505c\u7528" in replied.get("text", "")
