from __future__ import annotations

from datetime import timedelta

import httpx
from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)

from app.config import (
    ADMIN_TG_IDS,
    PUBLIC_BASE_URL,
    STARS_MONTHLY,
    TRIAL_DAYS,
    USDT_ADDRESS,
    USDT_CHAIN,
    USDT_YEARLY,
    WEBHOOK_BASE_URL,
    WEBHOOK_SECRET,
)
from app.crypto_token import encrypt_token
from app.db import get_session
from app.models import Identity, Order, Tenant, utcnow
from app.services import activate_order, add_event, get_or_create_tenant, new_code, open_order

TOKEN_RE = __import__("re").compile(r"^\d{6,}:[A-Za-z0-9_-]{20,}$")


def _kb_home() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("开始试用 / 绑定机器人", callback_data="bind")],
            [
                InlineKeyboardButton(f"Stars 月费 {STARS_MONTHLY}⭐", callback_data="pay_stars"),
                InlineKeyboardButton(f"USDT 年付 {USDT_YEARLY:g}", callback_data="pay_usdt"),
            ],
            [InlineKeyboardButton("我的状态", callback_data="status")],
        ]
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_session()
    try:
        tenant = get_or_create_tenant(db, update.effective_user.id)
        text = (
            "官方身份核验平台\n\n"
            "7 天试用：把你自己的 Bot Token 发给我，即可克隆出核验机器人。\n"
            "别人把可疑私聊转发到你的机器人，就能判断是不是本人。\n\n"
            f"当前状态：{tenant.status}\n"
            f"试用截止：{tenant.trial_ends_at}\n"
            f"已付到：{tenant.paid_until or '—'}\n"
            f"绑定机器人：@{tenant.bot_username or '未绑定'}"
        )
        await update.effective_message.reply_text(text, reply_markup=_kb_home())
    finally:
        db.close()


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    db = get_session()
    try:
        tenant = get_or_create_tenant(db, query.from_user.id)
        if data == "bind":
            await query.message.reply_text(
                "1. 打开 @BotFather\n2. 发送 /newbot\n3. 把 Token 在本对话发给我\n\nToken 会加密保存，消息随后删除。"
            )
            return
        if data == "status":
            await cmd_start(update, context)
            return
        if data == "pay_stars":
            await _create_stars(query, context, tenant, db)
            return
        if data == "pay_usdt":
            await _create_usdt(query, tenant, db)
            return
    finally:
        db.close()


async def _create_stars(query, context, tenant: Tenant, db) -> None:
    if open_order(db, tenant.id):
        await query.message.reply_text("你已有一笔待支付订单，请先完成或等待过期。")
        return
    payload = f"stars:{tenant.id}:{new_code()}"
    order = Order(
        public_code=new_code(),
        tenant_id=tenant.id,
        rail="stars",
        plan=tenant.plan or "pro",
        period_days=30,
        amount=STARS_MONTHLY,
        currency="XTR",
        status="pending",
        payload=payload,
        expires_at=utcnow() + timedelta(hours=24),
    )
    db.add(order)
    db.commit()
    await context.bot.send_invoice(
        chat_id=query.from_user.id,
        title="核验机器人 Pro 月费",
        description="30天托管 + 转发核验",
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice("30天", STARS_MONTHLY)],
        subscription_period=2592000,
    )


async def _create_usdt(query, tenant: Tenant, db) -> None:
    if not USDT_ADDRESS:
        await query.message.reply_text("平台尚未配置 USDT 收款地址，请用 Stars 月费。")
        return
    if open_order(db, tenant.id):
        await query.message.reply_text("你已有一笔待支付订单，请先完成或等待过期。")
        return
    code = new_code()
    url = f"{PUBLIC_BASE_URL}/pay/usdt/{code}"
    order = Order(
        public_code=code,
        tenant_id=tenant.id,
        rail="usdt",
        plan=tenant.plan or "pro",
        period_days=365,
        amount=USDT_YEARLY,
        currency="USDT",
        chain=USDT_CHAIN,
        pay_url=url,
        pay_address=USDT_ADDRESS,
        status="pending",
        expires_at=utcnow() + timedelta(minutes=20),
    )
    db.add(order)
    db.commit()
    await query.message.reply_text(
        f"已创建年付订单 {code}\n金额：{USDT_YEARLY:g} USDT（{USDT_CHAIN}）\n20 分钟内有效。\n{url}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("打开收银台", url=url)]]),
    )


async def on_precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.pre_checkout_query
    db = get_session()
    try:
        order = db.scalar(select(Order).where(Order.payload == q.invoice_payload))
        if not order or order.status != "pending":
            await q.answer(ok=False, error_message="订单无效或已关闭")
            return
        if int(order.amount) != q.total_amount:
            add_event(db, order, "failed", "stars_amount_mismatch")
            db.commit()
            await q.answer(ok=False, error_message="金额不一致")
            return
        await q.answer(ok=True)
    finally:
        db.close()


async def on_successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pay = update.message.successful_payment
    db = get_session()
    try:
        order = db.scalar(select(Order).where(Order.payload == pay.invoice_payload))
        if not order:
            await update.message.reply_text("付款已收到，但未找到订单，请联系管理员。")
            return
        if order.telegram_charge_id:
            await update.message.reply_text("这笔付款已经开通过。")
            return
        order.telegram_charge_id = pay.telegram_payment_charge_id
        add_event(db, order, "paid", "stars_successful_payment")
        tenant = activate_order(db, order)
        await update.message.reply_text(f"已开通至 {tenant.paid_until}")
    finally:
        db.close()


async def on_token(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or "").strip()
    if not TOKEN_RE.match(text):
        return
    db = get_session()
    try:
        tenant = get_or_create_tenant(db, update.effective_user.id)
        try:
            await update.message.delete()
        except Exception:
            pass
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(f"https://api.telegram.org/bot{text}/getMe")
            data = r.json()
        if not data.get("ok"):
            await update.effective_message.reply_text("Token 无效，请重新从 @BotFather 复制。")
            return
        me = data["result"]
        taken = db.scalar(select(Tenant).where(Tenant.bot_id == me["id"], Tenant.id != tenant.id))
        if taken:
            await update.effective_message.reply_text("这个机器人已被其他账号绑定。")
            return
        tenant.bot_id = me["id"]
        tenant.bot_username = me.get("username")
        tenant.bot_token_enc = encrypt_token(text)
        if not tenant.trial_ends_at:
            tenant.trial_ends_at = utcnow() + timedelta(days=TRIAL_DAYS)
        db.commit()
        if WEBHOOK_BASE_URL:
            url = f"{WEBHOOK_BASE_URL}/wh/t/{tenant.id}"
            async with httpx.AsyncClient(timeout=20) as client:
                await client.post(
                    f"https://api.telegram.org/bot{text}/setWebhook",
                    json={
                        "url": url,
                        "secret_token": WEBHOOK_SECRET,
                        "allowed_updates": ["message", "callback_query", "inline_query"],
                    },
                )
        ident = tenant.identity or Identity(tenant_id=tenant.id)
        if not ident.official_user_id:
            ident.official_user_id = update.effective_user.id
            ident.display_name = update.effective_user.full_name
            ident.username = update.effective_user.username or ""
            db.add(ident)
            db.commit()
        await update.effective_message.reply_text(
            f"已绑定 @{tenant.bot_username}\nWebhook 已设置。\n默认官方 ID：{ident.official_user_id}",
            reply_markup=_kb_home(),
        )
    finally:
        db.close()


async def cmd_setid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text("用法：/setid 你的Telegram数字ID")
        return
    db = get_session()
    try:
        tenant = get_or_create_tenant(db, update.effective_user.id)
        ident = tenant.identity or Identity(tenant_id=tenant.id)
        ident.official_user_id = int(context.args[0])
        db.add(ident)
        db.commit()
        await update.effective_message.reply_text(f"官方 User ID 已设为 {ident.official_user_id}")
    finally:
        db.close()


async def cmd_setname(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.effective_message.reply_text("用法：/setname 显示名")
        return
    db = get_session()
    try:
        tenant = get_or_create_tenant(db, update.effective_user.id)
        ident = tenant.identity or Identity(tenant_id=tenant.id)
        ident.display_name = " ".join(context.args)
        db.add(ident)
        db.commit()
        await update.effective_message.reply_text(f"显示名已设为 {ident.display_name}")
    finally:
        db.close()


async def cmd_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if ADMIN_TG_IDS and update.effective_user.id not in ADMIN_TG_IDS:
        return
    if not context.args:
        await update.effective_message.reply_text("用法：/confirm VH-XXXXXX [txid]")
        return
    db = get_session()
    try:
        order = db.scalar(select(Order).where(Order.public_code == context.args[0].upper()))
        if not order:
            await update.effective_message.reply_text("订单不存在")
            return
        if order.status in {"active", "paid"}:
            await update.effective_message.reply_text("订单已开通")
            return
        if len(context.args) > 1:
            order.txid = context.args[1]
        add_event(db, order, "paid", "manual_confirm")
        tenant = activate_order(db, order)
        await update.effective_message.reply_text(f"{order.public_code} 已开通至 {tenant.paid_until}")
    finally:
        db.close()


def build_platform_app(token: str) -> Application:
    app = Application.builder().token(token).updater(None).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("setid", cmd_setid))
    app.add_handler(CommandHandler("setname", cmd_setname))
    app.add_handler(CommandHandler("confirm", cmd_confirm))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(PreCheckoutQueryHandler(on_precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, on_successful_payment))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_token))
    return app
