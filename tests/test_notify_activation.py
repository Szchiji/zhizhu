"""Admin activation notify text formatting."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import asyncio

from app.notify import format_activation_text, notify_admins_activation


def test_format_activation_text_includes_fields():
    tenant = SimpleNamespace(
        owner_tg_id=123,
        paid_until=datetime(2027, 1, 1, 4, 0, tzinfo=timezone.utc),
        identity=SimpleNamespace(username="zhangsan"),
    )
    order = SimpleNamespace(rail="usdt", amount=99.5, plan="year", public_code="VH-TEST")
    text = format_activation_text(tenant, order, paid_label="一年", username="")
    assert "USDT" in text or "通道：USDT" in text
    assert "VH-TEST" in text
    assert "123" in text
    assert "@zhangsan" in text
    assert "一年" in text
    assert "2027" in text


def test_notify_admins_skips_without_bot(monkeypatch):
    monkeypatch.setattr("app.notify.ADMIN_TG_IDS", {1, 2})
    asyncio.run(notify_admins_activation(None, None, None))


def test_notify_admins_sends_to_each(monkeypatch):
    monkeypatch.setattr("app.notify.ADMIN_TG_IDS", {11, 22})
    bot = MagicMock()
    bot.send_message = AsyncMock()
    tenant = SimpleNamespace(owner_tg_id=9, paid_until=None, identity=None)
    order = SimpleNamespace(rail="stars", amount=100, plan="year", public_code="VH-X")
    asyncio.run(notify_admins_activation(bot, tenant, order, paid_label="一年"))
    assert bot.send_message.await_count == 2
