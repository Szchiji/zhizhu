"""UX polish: blocked users fail fast; cards show 有效期."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock


def test_fill_supports_expiry_placeholder(monkeypatch):
    from app.card_tpl import fill

    monkeypatch.setattr("app.card_tpl.brand_name", lambda: "VerifyHub")
    monkeypatch.setattr("app.card_tpl.bot_username", lambda: "vh_bot")
    out = fill("有效期：{有效期}", {"有效期": "2027-01-01 12:00"})
    assert "2027-01-01 12:00" in out


def test_card_text_includes_paid_until(monkeypatch):
    monkeypatch.setattr("app.card_tpl.brand_name", lambda: "VerifyHub")
    monkeypatch.setattr("app.card_tpl.bot_username", lambda: "vh_bot")

    # Avoid DB: force default templates
    def fake_load(db=None):
        from app.card_tpl import DEFAULTS
        return dict(DEFAULTS)

    monkeypatch.setattr("app.card_tpl.load_tpl", fake_load)

    from app.verify import card_text

    until = datetime(2027, 6, 1, 8, 0, tzinfo=timezone.utc)
    tenant = SimpleNamespace(paid_until=until, status="active", owner_tg_id=1)
    ident = SimpleNamespace(
        card_text="备注",
        display_name="张三",
        username="zhang",
        official_user_id=42,
        tenant=tenant,
    )
    text = card_text(ident)
    assert "有效期" in text
    assert "2027" in text


def test_inline_gates_before_thumb(monkeypatch):
    from app import inline_query as iq

    thumb_calls = {"n": 0}

    async def boom_thumb(bot):
        thumb_calls["n"] += 1
        raise AssertionError("thumb must not run for blocked user")

    async def deny_gate(uid):
        return "账号已被停用，无法使用本机器人。", ""

    # Patch whatever the module actually names these
    thumb_name = "_thumb" if hasattr(iq, "_thumb") else None
    gate_name = "gate_user" if hasattr(iq, "gate_user") else None
    on_name = "on_inline" if hasattr(iq, "on_inline") else None
    assert thumb_name and gate_name and on_name, (dir(iq),)

    monkeypatch.setattr(iq, thumb_name, boom_thumb)
    monkeypatch.setattr(iq, gate_name, deny_gate)

    answered = {}

    async def fake_answer(results, **kwargs):
        answered["results"] = results
        answered["kwargs"] = kwargs

    q = MagicMock()
    q.from_user = SimpleNamespace(id=99)
    q.query = "@someone"
    q.id = "qid"
    q.answer = fake_answer
    update = MagicMock(inline_query=q)
    context = MagicMock()

    asyncio.run(getattr(iq, on_name)(update, context))
    assert thumb_calls["n"] == 0
    assert answered["kwargs"].get("cache_time") == 0
    assert answered["kwargs"].get("is_personal") is True
    content = answered["results"][0].input_message_content
    body = getattr(content, "message_text", None) or str(content)
    assert "停用" in body
