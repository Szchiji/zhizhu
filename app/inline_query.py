from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent, Update
from telegram.ext import ContextTypes

from app.brand import brand_name, bot_username
from app.db import get_session
from app.services import parse_username, resolve_paid_identity
from app.verify import card_kb, card_text, promo_text

log = logging.getLogger("zhizhu.inline")


async def on_inline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.inline_query
    if not q:
        return
    bot_name = (context.bot.username or bot_username() or "bot").lstrip("@")
    brand = brand_name() or "官方核验"
    name = parse_username(q.query or "")
    ident = None
    db = get_session()
    try:
        if name:
            ident = await resolve_paid_identity(db, name, context.bot)
    except Exception:
        log.exception("inline resolve")
    finally:
        db.close()
    try:
        if ident:
            title = f"✅ @{ident.username or name} 官方登记"
            desc = f"{ident.display_name or ''} · ID {ident.official_user_id or '—'}".strip(" ·")
            body = card_text(ident, bot_username=bot_name)
            markup = card_kb(ident, bot_username=bot_name)
        else:
            title = f"查询 @{name}" if name else f"{brand}·官方核验"
            desc = "点击发送查询结果" if name else "输入用户名查询，或点击开通"
            body = promo_text(bot_name, name)
            markup = InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("查询更多", url=f"https://t.me/{bot_name}?start={'q_'+name if name else 'ask'}")],
                    [InlineKeyboardButton("开通官方核验", url=f"https://t.me/{bot_name}?start=pay")],
                ]
            )
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
                        title=f"{brand}查询",
                        description="点击发送",
                        input_message_content=InputTextMessageContent(promo_text(bot_name, name)),
                    )
                ],
                cache_time=0,
                is_personal=True,
            )
        except Exception:
            log.exception("inline fallback")
