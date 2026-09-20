"""Bot admin text/callback mutations write AdminAudit (mocked session)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import AdminAudit


def _admin_update(uid: int = 42):
    update = MagicMock()
    update.effective_user.id = uid
    update.effective_message.reply_text = AsyncMock()
    return update


def _context(wait: str):
    ctx = MagicMock()
    ctx.user_data = {"wait": wait}
    return ctx


def _audit_actions(db: MagicMock) -> list[str]:
    out = []
    for call in db.add.call_args_list:
        if not call.args:
            continue
        row = call.args[0]
        if isinstance(row, AdminAudit):
            out.append(row.action)
    return out


def _run(coro):
    return asyncio.run(coro)


def test_admin_addr_text_writes_audit():
    from app import platform_bot as pb

    db = MagicMock()
    update = _admin_update()
    ctx = _context("admin_addr")
    addr = "T" + ("A" * 33)

    with (
        patch.object(pb, "get_session", return_value=db),
        patch.object(pb, "_is_admin", return_value=True),
        patch.object(pb, "set_setting") as set_setting,
        patch.object(pb, "_kb_admin", return_value=None),
    ):
        ok = _run(pb._handle_admin_text(update, ctx, addr))

    assert ok is True
    set_setting.assert_called_once_with(db, "usdt_address", addr)
    assert "addr" in _audit_actions(db)
    db.commit.assert_called()
    assert ctx.user_data.get("wait") is None


def test_admin_price_text_writes_audit():
    from app import platform_bot as pb

    db = MagicMock()
    update = _admin_update()
    ctx = _context("admin_price:year:stars")

    with (
        patch.object(pb, "get_session", return_value=db),
        patch.object(pb, "_is_admin", return_value=True),
        patch.object(pb, "set_setting") as set_setting,
        patch.object(pb, "price_board", return_value="board"),
        patch.object(pb, "_kb_admin", return_value=None),
    ):
        ok = _run(pb._handle_admin_text(update, ctx, "120"))

    assert ok is True
    set_setting.assert_called_once_with(db, "stars_year", "120")
    assert "price" in _audit_actions(db)
    row = next(c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], AdminAudit))
    assert row.target_id == "stars_year"
    assert "amount=120" in (row.detail or "")


def test_admin_clone_callback_writes_audit():
    from app import platform_bot as pb

    db = MagicMock()
    query = MagicMock()
    query.from_user.id = 42
    query.message.reply_text = AsyncMock()
    ctx = MagicMock()

    with (
        patch.object(pb, "_is_admin", return_value=True),
        patch.object(pb, "clone_on", return_value=False),
        patch.object(pb, "set_clone") as set_clone,
        patch.object(pb, "_kb_admin", return_value=None),
    ):
        ok = _run(pb._admin_cb(query, ctx, "adm:clone", db))

    assert ok is True
    set_clone.assert_called_once_with(db, True)
    assert "clone" in _audit_actions(db)
    db.commit.assert_called()
