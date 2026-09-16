from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent, Update
from app.models import Identity, Tenant
from app.services import tenant_usable


def _card(ident: Identity, watermark: bool) -> str:
    name = ident.display_name or "未设置"
    uname = f"@{ident.username}" if ident.username else "无用户名"
    uid = ident.official_user_id or "未设置"
    extra = "\n\nPowered by 核验平台" if watermark else ""
    return (
        f"官方身份\n"
        f"{name}（{uname}）\n"
        f"User ID：{uid}\n"
        f"只认这一个号，其他同名都不是本人。"
        f"{extra}"
    )


def _kb(ident: Identity) -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton("确认是本人", callback_data="info")]
    if ident.username:
        row.append(InlineKeyboardButton("私聊正主", url=f"https://t.me/{ident.username.lstrip('@')}"))
    elif ident.official_user_id:
        row.append(InlineKeyboardButton("打开资料", url=f"tg://user?id={ident.official_user_id}"))
    return InlineKeyboardMarkup([row])


def _alert(ident: Identity) -> str:
    text = ident.alert_text or "这是公示的官方账号，只认这一个号"
    uid = ident.official_user_id or ""
    uname = f"@{ident.username}" if ident.username else ""
    out = f"{text}\n{uname}\nID {uid}".strip()
    return out[:200]


async def handle_tenant_update(update: Update, tenant: Tenant, bot) -> None:
    if not tenant_usable(tenant):
        if update.effective_message:
            await update.effective_message.reply_text(
                "套餐已到期。请打开平台机器人续费：Stars 月费或 USDT 年付。"
            )
        elif update.callback_query:
            await update.callback_query.answer("套餐已到期，请先续费", show_alert=True)
        elif update.inline_query:
            await update.inline_query.answer([], cache_time=10)
        return

    ident = tenant.identity or Identity()
    watermark = tenant.status == "trial" and not (tenant.paid_until and tenant.trial_ends_at and tenant.paid_until > tenant.trial_ends_at)

    if update.inline_query:
        q = update.inline_query
        await q.answer(
            [
                InlineQueryResultArticle(
                    id="official",
                    title=f"{ident.display_name or '官方身份'} · 核验卡",
                    description="发送官方身份卡",
                    input_message_content=InputTextMessageContent(_card(ident, watermark)),
                    reply_markup=_kb(ident),
                )
            ],
            cache_time=10,
            is_personal=True,
        )
        return

    if update.callback_query:
        cq = update.callback_query
        if cq.data == "info":
            await cq.answer(_alert(ident), show_alert=True)
        else:
            await cq.answer()
        return

    msg = update.effective_message
    if not msg:
        return

    if msg.forward_origin or msg.forward_from or msg.forward_date:
        src_id = None
        src_name = "未知"
        if msg.forward_from:
            src_id = msg.forward_from.id
            src_name = msg.forward_from.full_name
        elif getattr(msg, "forward_origin", None) is not None:
            origin = msg.forward_origin
            user = getattr(origin, "sender_user", None)
            if user:
                src_id = user.id
                src_name = user.full_name
        official = ident.official_user_id
        if official and src_id == official:
            result = f"核验结果：是本人\n来源：{src_name}\nID：{src_id}"
        elif official and src_id:
            result = (
                f"核验结果：不是本人\n"
                f"来源：{src_name}\n来源 ID：{src_id}\n官方 ID：{official}\n"
                f"请不要转账，先打电话确认。"
            )
        else:
            result = "无法判断。请先在平台机器人用 /setid 设置官方 User ID。\n若对方关闭了转发来源，也核验不了。"
        await msg.reply_text(result, reply_markup=_kb(ident))
        return

    await msg.reply_text(_card(ident, watermark), reply_markup=_kb(ident))
