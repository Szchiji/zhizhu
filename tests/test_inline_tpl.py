"""Inline title/description templates: defaults, fill, persist, truncate, wiring."""
from __future__ import annotations

from types import SimpleNamespace
import asyncio
from unittest.mock import AsyncMock

from app.db import get_session, init_db
from app.inline_tpl import (
    DEFAULTS,
    EMPTY_UNPAID,
    DESC_MAX,
    TITLE_MAX,
    fill,
    load_tpl,
    render,
    save_tpl,
    _truncate,
)
from app.services import get_setting


def setup_function():
    init_db()


def test_defaults_match_legacy_hardcodes(monkeypatch):
    monkeypatch.setattr("app.inline_tpl.brand_name", lambda: "VerifyHub")
    monkeypatch.setattr("app.inline_tpl.bot_username", lambda: "vh_bot")
    # paid
    assert (
        render("paid", "title", {"账号": "@alice"}, db=None)
        == "✅ @alice 平台登记"
    )
    assert (
        render("paid", "description", {"姓名": "爱丽丝", "ID": "42"}, db=None)
        == "爱丽丝 · ID 42"
    )
    # paid empty name strips leading ·
    assert render("paid", "description", {"姓名": "", "ID": "9"}, db=None) == "ID 9"
    # unpaid with query
    assert render("unpaid", "title", {"查询词": "bob"}, db=None) == "查询 @bob"
    assert render("unpaid", "description", {"查询词": "bob"}, db=None) == "点击发送登记卡"
    # unpaid empty query → promo
    assert render("unpaid", "title", {"查询词": ""}, db=None) == "VerifyHub·平台登记"
    assert render("unpaid", "description", {"查询词": ""}, db=None) == "输入用户名查询"
    assert EMPTY_UNPAID["title"] == "{品牌}·平台登记"
    # issuer
    assert render("issuer", "title", {}, db=None) == "🛡️ VerifyHub 平台出具方"
    assert render("issuer", "description", {}, db=None) == "本账号为平台登记机器人"
    # clone
    assert render("clone", "title", {"姓名": "平台登记"}, db=None) == "平台登记 · 登记卡"
    assert render("clone", "description", {}, db=None) == "发送平台登记卡"
    assert DEFAULTS["paid"]["title"] == "✅ {账号} 平台登记"


def test_fill_strips_tags_plain():
    out = fill("Hi {姓名}", {"姓名": "<b>Tom</b><script>x</script>"})
    assert "<b>" not in out
    assert "<script>" not in out
    assert "Tom" in out
    assert "x" in out


def test_save_load_roundtrip(monkeypatch):
    monkeypatch.setattr("app.inline_tpl.brand_name", lambda: "VerifyHub")
    monkeypatch.setattr("app.inline_tpl.bot_username", lambda: "vh_bot")
    db = get_session()
    save_tpl(
        db,
        {
            "inline_tpl": {
                "paid": {"title": "CUSTOM ✅ {账号}", "description": "DESC {姓名}"},
                "unpaid": {"title": "查 {查询词}", "description": "点一下"},
            }
        },
    )
    db.close()
    db2 = get_session()
    loaded = load_tpl(db2)
    assert loaded["paid"]["title"] == "CUSTOM ✅ {账号}"
    assert "CUSTOM ✅ @x" == render("paid", "title", {"账号": "@x"}, db=db2)
    assert get_setting(db2, "inline_tpl_paid_title", "").startswith("CUSTOM")
    # HTML stripped on save
    save_tpl(db2, {"paid": {"title": "<b>粗</b>{账号}", "description": "d"}})
    again = load_tpl(db2)
    assert "<b>" not in again["paid"]["title"]
    assert "粗{账号}" == again["paid"]["title"]
    db2.close()


def test_truncation():
    long = "字" * 200
    assert len(_truncate(long, TITLE_MAX)) <= TITLE_MAX
    assert len(_truncate(long, DESC_MAX)) <= DESC_MAX
    assert _truncate(long, TITLE_MAX).endswith("…")
    out = render("paid", "title", {"账号": "@" + ("a" * 80)}, db=None)
    assert len(out) <= TITLE_MAX


def test_inline_query_uses_template(monkeypatch):
    monkeypatch.setattr("app.inline_tpl.brand_name", lambda: "VerifyHub")
    monkeypatch.setattr("app.inline_tpl.bot_username", lambda: "vh_bot")
    monkeypatch.setattr("app.inline_query.brand_name", lambda: "VerifyHub")
    monkeypatch.setattr("app.inline_query.bot_username", lambda: "vh_bot")
    db = get_session()
    save_tpl(
        db,
        {"inline_tpl": {"unpaid": {"title": "TPL查询 @{查询词}", "description": "TPL点发送"}}},
    )
    db.close()

    from app.inline_query import on_inline

    answered = {}

    async def fake_answer(results, **kwargs):
        answered["results"] = results
        answered["kwargs"] = kwargs

    q = SimpleNamespace(
        id="iq1",
        query="@someone",
        from_user=SimpleNamespace(id=1),
        answer=fake_answer,
    )
    update = SimpleNamespace(inline_query=q)
    bot = SimpleNamespace(
        id=99,
        username="vh_bot",
        get_user_profile_photos=AsyncMock(return_value=SimpleNamespace(photos=[])),
    )
    context = SimpleNamespace(bot=bot)

    async def no_gate(uid):
        return None, None

    monkeypatch.setattr("app.inline_query.gate_user", no_gate)
    monkeypatch.setattr("app.inline_query.parse_username", lambda raw: "someone")
    monkeypatch.setattr("app.inline_query.is_platform_bot", lambda *a, **k: False)
    monkeypatch.setattr("app.inline_query.resolve_paid_identity", AsyncMock(return_value=None))
    monkeypatch.setattr("app.inline_query.promo_text", lambda *a, **k: "body")
    monkeypatch.setattr("app.inline_query.card_kb", lambda *a, **k: None)
    monkeypatch.setattr("app.inline_query.parse_mode_for", lambda db: None)
    monkeypatch.setattr("app.inline_query._thumb", AsyncMock(return_value=""))

    asyncio.run(on_inline(update, context))
    assert answered["results"]
    art = answered["results"][0]
    assert art.title == "TPL查询 @someone"
    assert art.description == "TPL点发送"


def test_mini_asset_ver_inline():
    from app.static_ver import MINI_ASSET_VER

    assert MINI_ASSET_VER >= 19


def test_mini_injects_inline_js():
    from fastapi.testclient import TestClient
    from app.main import app

    c = TestClient(app)
    r = c.get("/mini-inline.js")
    assert r.status_code == 200
    assert "内联列表标题" in r.text or "inline_tpl" in r.text
    r2 = c.get("/mini")
    assert r2.status_code == 200
    assert "mini-inline.js" in r2.text
