from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.access import get_bot
from app.brand import bot_username
from app.db import get_session
from app.models import Tenant, utcnow
from app.services import get_setting, set_setting

log = logging.getLogger("zhizhu.renew")
_task: asyncio.Task | None = None


async def sweep_reminders() -> int:
    bot = get_bot()
    if bot is None:
        return 0
    db = get_session()
    sent = 0
    try:
        if get_setting(db, "remind_enabled", "1") == "0":
            return 0
        try:
            days = max(1, min(90, int(get_setting(db, "remind_days", "7") or 7)))
        except ValueError:
            days = 7
        text = (get_setting(db, "remind_text", "") or "你的官方核验即将到期，打开小程序续费可叠加时效。").strip()
        now = utcnow()
        end = now + timedelta(days=days)
        rows = list(
            db.scalars(
                select(Tenant).where(
                    Tenant.paid_until.is_not(None),
                    Tenant.paid_until > now,
                    Tenant.paid_until <= end,
                    Tenant.status != "suspended",
                )
            )
        )
        bot_name = (bot_username() or "").lstrip("@")
        kb = None
        if bot_name:
            kb = InlineKeyboardMarkup(
                [[InlineKeyboardButton("去续费", url=f"https://t.me/{bot_name}?startapp")]]
            )
        for tenant in rows:
            if tenant.status == "owner":
                continue
            stamp = tenant.paid_until.date().isoformat() if tenant.paid_until else ""
            key = f"reminded:{tenant.id}:{stamp}"
            if get_setting(db, key):
                continue
            try:
                await bot.send_message(chat_id=int(tenant.owner_tg_id), text=text[:1000], reply_markup=kb)
                set_setting(db, key, "1")
                sent += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("remind fail tg=%s: %s", tenant.owner_tg_id, exc)
        return sent
    finally:
        db.close()


async def _loop() -> None:
    await asyncio.sleep(20)
    while True:
        try:
            n = await sweep_reminders()
            if n:
                log.info("renew reminders sent=%s", n)
        except Exception as exc:  # noqa: BLE001
            log.warning("renew sweep failed: %s", exc)
        await asyncio.sleep(6 * 3600)


def start_renew_job() -> None:
    global _task
    if _task and not _task.done():
        return
    try:
        _task = asyncio.get_event_loop().create_task(_loop())
    except Exception as exc:  # noqa: BLE001
        log.warning("renew job not started: %s", exc)
