from __future__ import annotations

from telegram import InlineQueryResultArticle, InputTextMessageContent, Update

from app.models import Identity, Tenant
from app.services import tenant_usable
from app.card_tpl import parse_mode_for
from app.db import get_session
from app.verify import PARSE_MODE, alert_text, card_kb, card_text, extract_forward, is_forwarded, judge


async def handle_tenant_update(update: Update, tenant: Tenant, bot) -> None:
    if not tenant_usable(tenant):
        if update.effective_message:
            await update.effective_message.reply_text(
                "套餐已到期。请打开平台机器人续费，也可直接用平台机器人核验和引流。"
            )
        elif update.callback_query:
            await update.callback_query.answer("套餐已到期，请先续费", show_alert=True)
        elif update.inline_query:
            await update.inline_query.answer([], cache_time=10)
        return

    ident = tenant.identity or Identity()
    watermark = tenant.status == "trial"
    me = await bot.get_me()
    bot_username = me.username or ""
    db = get_session()
    try:
        mode = parse_mode_for(db) or PARSE_MODE
        card_body = card_text(ident, watermark=watermark, bot_username=bot_username, db=db)
    finally:
        db.close()

    if update.inline_query:
        q = update.inline_query
        await q.answer(
            [
                InlineQueryResultArticle(
                    id="official",
                    title=f"{ident.display_name or '平台登记'} · 登记卡",
                    description="发送平台登记卡",
                    input_message_content=InputTextMessageContent(
                        card_body,
                        parse_mode=mode,
                    ),
                    reply_markup=card_kb(ident, bot_username=bot_username),
                )
            ],
            cache_time=0,
            is_personal=True,
        )
        return

    if update.callback_query:
        cq = update.callback_query
        if cq.data == "info":
            await cq.answer(alert_text(ident), show_alert=True)
        else:
            await cq.answer()
        return

    msg = update.effective_message
    if not msg:
        return

    if is_forwarded(msg):
        src_id, src_name = extract_forward(msg)
        await msg.reply_text(
            judge(ident, src_id, src_name),
            reply_markup=card_kb(ident, bot_username=bot_username),
        )
        return

    await msg.reply_text(
        card_body,
        reply_markup=card_kb(ident, bot_username=bot_username),
        parse_mode=mode,
    )
