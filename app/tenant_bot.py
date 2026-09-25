from __future__ import annotations

from telegram import InlineQueryResultArticle, InputTextMessageContent, Update

from app.models import Identity, Tenant
from app.services import tenant_usable
from app.card_tpl import parse_mode_for
from app.db import get_session
from app import inline_tpl
from app.verify import PARSE_MODE, alert_text, card_kb, card_text, extract_forward, is_forwarded, judge


async def handle_tenant_update(update: Update, tenant: Tenant, bot) -> None:
    from app.saas_clones import is_clone_disabled

    _db = get_session()
    try:
        _disabled = is_clone_disabled(_db, tenant.id)
    finally:
        _db.close()
    if _disabled:
        if update.effective_message:
            await update.effective_message.reply_text("\u514b\u9686\u5b9e\u4f8b\u5df2\u7531\u5e73\u53f0\u505c\u7528\uff0c\u8bf7\u8054\u7cfb\u7ba1\u7406\u5458\u3002")
        elif update.callback_query:
            await update.callback_query.answer("\u514b\u9686\u5b9e\u4f8b\u5df2\u505c\u7528", show_alert=True)
        elif update.inline_query:
            await update.inline_query.answer([], cache_time=10)
        return

    if not tenant_usable(tenant):
        if update.effective_message:
            await update.effective_message.reply_text(
                "\u5957\u9910\u5df2\u5230\u671f\u3002\u8bf7\u6253\u5f00\u5e73\u53f0\u673a\u5668\u4eba\u7eed\u8d39\uff0c\u4e5f\u53ef\u76f4\u63a5\u7528\u5e73\u53f0\u673a\u5668\u4eba\u6838\u9a8c\u548c\u5f15\u6d41\u3002"
            )
        elif update.callback_query:
            await update.callback_query.answer("\u5957\u9910\u5df2\u5230\u671f\uff0c\u8bf7\u5148\u7eed\u8d39", show_alert=True)
        elif update.inline_query:
            await update.inline_query.answer([], cache_time=10)
        return

    ident = tenant.identity or Identity()
    watermark = tenant.status == "trial"
    me = await bot.get_me()
    bot_username = me.username or ""
    iq_title = ""
    iq_desc = ""
    db = get_session()
    try:
        mode = parse_mode_for(db) or PARSE_MODE
        card_body = card_text(ident, watermark=watermark, bot_username=bot_username, db=db)
        if update.inline_query:
            extra = {
                "\u59d3\u540d": ident.display_name or "\u5e73\u53f0\u767b\u8bb0",
                "\u8d26\u53f7": f"@{ident.username}" if getattr(ident, "username", None) else "\u672a\u7ed1\u5b9a",
                "ID": getattr(ident, "official_user_id", None) or "\u2014",
                "\u673a\u5668\u4eba": bot_username,
            }
            iq_title = inline_tpl.render("clone", "title", extra, db=db)
            iq_desc = inline_tpl.render("clone", "description", extra, db=db)
    finally:
        db.close()

    if update.inline_query:
        q = update.inline_query
        await q.answer(
            [
                InlineQueryResultArticle(
                    id="official",
                    title=iq_title,
                    description=iq_desc,
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
