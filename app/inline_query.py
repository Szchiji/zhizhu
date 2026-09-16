from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent, Update, WebAppInfo
from telegram.ext import ContextTypes

from app.access import gate_user
from app.brand import brand_name, bot_username
from app.config import PUBLIC_BASE_URL, WEBHOOK_BASE_URL
from app.db import get_session
from app.services import parse_username, resolve_paid_identity
from app.verify import card_kb, card_text, promo_text


def _mini() -> str:
    base = (PUBLIC_BASE_URL or WEBHOOK_BASE_URL or "").rstrip("/")
    return f"{base}/mini" if base.startswith("https://") else ""


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
        ident = await resolve_paid_identity(db, name, context.bot) if name else None
    finally:
        db.close()
    mini = _mini()
    if ident:
        title = f"✅ @{ident.username or name} 官方登记"
        desc = f"{ident.display_name or ''} · ID {ident.official_user_id or '—'}".strip(" ·")
        body = card_text(ident, bot_username=bot_name)
        markup = card_kb(ident, bot_username=bot_name)
    else:
        title = f"查询 @{name}" if name else f"{brand}·官方核验"
        desc = f"点击发送，消息带 @{bot_name} 来源"
        body = promo_text(bot_name, name)
        pay = (
            InlineKeyboardButton("开通官方核验", web_app=WebAppInfo(url=mini))
            if mini
            else InlineKeyboardButton("开通官方核验", url=f"https://t.me/{bot_name}?start=pay")
        )
        markup = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("查询更多", url=f"https://t.me/{bot_name}?start={'q_'+name if name else 'ask'}")],
                [pay],
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
