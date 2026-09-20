from __future__ import annotations

import logging

from telegram import InlineQueryResultArticle, InputTextMessageContent, Update
from telegram.ext import ContextTypes

from app.access import gate_user
from app.brand import brand_name, bot_username
from app.config import PUBLIC_BASE_URL, WEBHOOK_BASE_URL
from app.db import get_session
from app.services import parse_username, resolve_paid_identity
from app.card_tpl import parse_mode_for
from app.verify import PARSE_MODE, card_kb, card_text, issuer_kb, issuer_text, is_platform_bot, promo_text

log = logging.getLogger("zhizhu.inline")


def _thumb_base() -> str:
    base = (PUBLIC_BASE_URL or WEBHOOK_BASE_URL or "").rstrip("/")
    return f"{base}/avatar" if base.startswith("https://") else ""


async def _thumb(bot) -> str:
    base = _thumb_base()
    if not base:
        return ""
    tag = "0"
    try:
        photos = await bot.get_user_profile_photos(bot.id, limit=1)
        if photos.photos:
            tag = photos.photos[0][-1].file_unique_id or "0"
    except Exception:
        log.exception("avatar version")
    return f"{base}?f={tag}"


def _article(thumb: str, **kwargs) -> InlineQueryResultArticle:
    if thumb:
        kwargs["thumbnail_url"] = thumb
        kwargs["thumbnail_width"] = 320
        kwargs["thumbnail_height"] = 320
    return InlineQueryResultArticle(**kwargs)


async def on_inline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.inline_query
    if not q:
        return
    uid = q.from_user.id if q.from_user else 0
    # Fail suspended/blocked users immediately (before avatar thumb fetch).
    reason, _url = await gate_user(uid)
    if reason:
        try:
            await q.answer(
                [
                    _article(
                        "",
                        id="denied",
                        title="暂不可用",
                        description=reason[:64],
                        input_message_content=InputTextMessageContent(reason),
                    )
                ],
                cache_time=0,
                is_personal=True,
            )
        except Exception:
            log.exception("inline deny")
        return
    thumb = await _thumb(context.bot)
    bot_name = (bot_username() or context.bot.username or "bot").lstrip("@")
    brand = brand_name() or "平台登记"
    raw = (q.query or "").strip()
    name = parse_username(raw) or raw.lstrip("@").split()[0] if raw else ""
    title = f"查询 @{name}" if name else f"{brand}·平台登记"
    desc = "点击发送登记卡" if name else "输入用户名查询"
    markup = card_kb(username=name, bot_username=bot_name)
    body = ""
    mode = PARSE_MODE
    db = get_session()
    try:
        mode = parse_mode_for(db) or PARSE_MODE
        if name and is_platform_bot(name, context.bot.username or bot_name):
            title = f"🛡️ {brand} 平台出具方"
            desc = "本账号为平台登记机器人"
            body = issuer_text(bot_name, db=db)
            markup = issuer_kb(bot_name)
        else:
            body = promo_text(bot_name, name, db=db)
            try:
                ident = await resolve_paid_identity(db, name, context.bot) if name else None
                if ident:
                    name = ident.username or name
                    title = f"✅ @{name} 平台登记"
                    desc = f"{ident.display_name or ''} · ID {ident.official_user_id or '—'}".strip(" ·")
                    body = card_text(ident, bot_username=bot_name, db=db)
                    markup = card_kb(ident, bot_username=bot_name)
            except Exception:
                log.exception("inline resolve")
    finally:
        db.close()
    item = _article(
        thumb,
        id=(q.id or "r1")[:64],
        title=title,
        description=desc,
        input_message_content=InputTextMessageContent(body, parse_mode=mode),
        reply_markup=markup,
    )
    try:
        await q.answer([item], cache_time=0, is_personal=True, switch_pm_text="打开小程序", switch_pm_parameter="pay")
    except Exception:
        log.exception("inline answer")
        try:
            await q.answer([item], cache_time=0, is_personal=True)
        except Exception:
            log.exception("inline fallback")
