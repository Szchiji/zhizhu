from __future__ import annotations

import logging

from telegram import InlineQueryResultArticle, InputTextMessageContent, Update
from telegram.ext import ContextTypes

from app.access import gate_user
from app.brand import brand_name, bot_username
from app.db import get_session
from app.services import parse_username, resolve_paid_identity
from app.verify import card_kb, card_text, promo_text

log = logging.getLogger("zhizhu.inline")


async def on_inline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.inline_query
    if not q:
        return
    uid = q.from_user.id if q.from_user else 0
    reason, _url = await gate_user(uid)
    if reason:
        try:
            await q.answer(
                [
                    InlineQueryResultArticle(
                        id="denied",
                        title="暂不可用",
                        description=reason,
                        input_message_content=InputTextMessageContent(reason),
                    )
                ],
                cache_time=0,
                is_personal=True,
            )
        except Exception:
            log.exception("inline deny")
        return
    bot_name = (context.bot.username or bot_username() or "bot").lstrip("@")
    brand = brand_name() or "官方核验"
    raw = (q.query or "").strip()
    name = parse_username(raw) or raw.lstrip("@").split()[0] if raw else ""
    title = f"查询 @{name}" if name else f"{brand}·官方核验"
    desc = "点击发送官方卡" if name else "输入用户名查询"
    body = promo_text(bot_name, name)
    uname = name
    db = get_session()
    try:
        ident = await resolve_paid_identity(db, name, context.bot) if name else None
        if ident:
            uname = ident.username or name
            title = f"✅ @{uname} 官方登记"
            desc = f"{ident.display_name or ''} · ID {ident.official_user_id or '—'}".strip(" ·")
            body = card_text(ident, bot_username=bot_name)
    except Exception:
        log.exception("inline resolve")
    finally:
        db.close()
    markup = card_kb(username=uname, bot_username=bot_name)
    try:
        await q.answer(
            [
                InlineQueryResultArticle(
                    id=(q.id or "r1")[:64],
                    title=title,
                    description=desc,
                    input_message_content=InputTextMessageContent(body),
                    reply_markup=markup,
                )
            ],
            cache_time=0,
            is_personal=True,
            switch_pm_text="打开小程序",
            switch_pm_parameter="pay",
        )
    except Exception:
        log.exception("inline answer")
        try:
            await q.answer(
                [
                    InlineQueryResultArticle(
                        id="fallback",
                        title=title,
                        description=desc,
                        input_message_content=InputTextMessageContent(body),
                        reply_markup=markup,
                    )
                ],
                cache_time=0,
                is_personal=True,
            )
        except Exception:
            log.exception("inline fallback")
