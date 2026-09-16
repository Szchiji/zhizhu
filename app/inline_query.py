from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent, Update
from telegram.ext import ContextTypes

from app.access import gate_user
from app.brand import brand_name, bot_username
from app.db import get_session
from app.services import find_paid_identity, parse_username
from app.verify import card_kb, card_text, promo_text


async def on_inline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.inline_query
    deny, _ = await gate_user(q.from_user.id if q.from_user else 0)
    if deny:
        await q.answer([], cache_time=0, is_personal=True)
        return
    bot_name = (context.bot.username or bot_username()).lstrip("@")
    brand = brand_name()
    name = parse_username(q.query or "")
    db = get_session()
    try:
        ident = find_paid_identity(db, name) if name else None
    finally:
        db.close()
    if ident:
        title = f"✅ @{ident.username or name} 官方登记"
        desc = f"{ident.display_name or ''} · ID {ident.official_user_id or '—'}".strip(" ·")
        body = card_text(ident, bot_username=bot_name)
        markup = card_kb(ident, bot_username=bot_name)
    else:
        title = f"查询 @{name}" if name else f"{brand}·官方核验"
        desc = f"点击发送，消息带 @{bot_name} 来源"
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
    )
