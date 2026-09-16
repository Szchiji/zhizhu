from __future__ import annotations

from datetime import timedelta

import httpx
from sqlalchemy import select
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
    LabeledPrice,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    InlineQueryHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)

from app.config import (
    ADMIN_TG_IDS,
    PUBLIC_BASE_URL,
    TRIAL_DAYS,
    USDT_ADDRESS,
    USDT_CHAIN,
    WEBHOOK_BASE_URL,
    WEBHOOK_SECRET,
)
from app.crypto_token import encrypt_token
from app.db import get_session
from app.models import Identity, Order, Tenant, utcnow
from app.services import (
    activate_order,
    add_event,
    get_or_create_tenant,
    get_setting,
    is_staff,
    new_code,
    open_order,
    set_setting,
    stars_price,
    usdt_price,
)
from app.verify import card_kb, card_text, share_url

TOKEN_RE = __import__("re").compile(r"^\d{6,}:[A-Za-z0-9_-]{20,}$")


def _is_admin(user_id: int) -> bool:
    return bool(ADMIN_TG_IDS) and user_id in ADMIN_TG_IDS


def _pay_address(db) -> str:
    return get_setting(db, "usdt_address", USDT_ADDRESS)


def _kb_home(stars: int, usdt: float) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("开始试用 / 绑定机器人", callback_data="bind")],
            [
                InlineKeyboardButton(f"Stars 月费 {stars}⭐", callback_data="pay_stars"),
                InlineKeyboardButton(f"USDT 年付 {usdt:g}", callback_data="pay_usdt"),
            ],
            [InlineKeyboardButton("我的状态", callback_data="status")],
        ]
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_session()
    try:
        user = update.effective_user
        tenant = get_or_create_tenant(db, user.id)
        if tenant.identity:
            if user.username:
                tenant.identity.username = user.username
            if not tenant.identity.official_user_id:
                tenant.identity.official_user_id = user.id
            if not tenant.identity.display_name:
                tenant.identity.display_name = user.full_name
            db.commit()
        text = (
            "官方身份核验平台\n\n"
            "直接用本机器人核验，不用提交自己的 Bot Token。\n"
            "在任何对话输入 @"
            f"{context.bot.username or 'zhizhusp_bot'} 加空格，点出现的核验卡即可发给朋友。\n\n"
            f"当前状态：{tenant.status}\n"
            f"试用截止：{tenant.trial_ends_at}\n"
            f"已付到：{tenant.paid_until or '—'}\n"
            f"绑定机器人：@{tenant.bot_username or '未绑定'}"
        )
        await update.effective_message.reply_text(
            text, reply_markup=_kb_home(stars_price(db), usdt_price(db))
        )
    finally:
        db.close()


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)


async def on_inline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.inline_query
    db = get_session()
    try:
        user = q.from_user
        tenant = get_or_create_tenant(db, user.id)
        if tenant.identity:
            if user.username:
                tenant.identity.username = user.username
            if not tenant.identity.official_user_id:
                tenant.identity.official_user_id = user.id
            if not tenant.identity.display_name:
                tenant.identity.display_name = user.full_name
            db.commit()
        ident = tenant.identity or Identity()
        bot_name = context.bot.username or "zhizhusp_bot"
        url = share_url(bot_name, tenant.id)
        await q.answer(
            [
                InlineQueryResultArticle(
                    id=f"card-{tenant.id}",
                    title=f"{ident.display_name or '官方身份'} · 核验卡",
                    description="点击发送官方身份核验卡",
                    input_message_content=InputTextMessageContent(
                        card_text(ident, watermark=True, bot_username=bot_name)
                    ),
                    reply_markup=card_kb(ident, share_url=url, bot_username=bot_name),
                )
            ],
            cache_time=1,
            is_personal=True,
        )
    except Exception:
        await q.answer([], cache_time=1)
    finally:
        db.close()


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    db = get_session()
    try:
        tenant = get_or_create_tenant(db, query.from_user.id)
        if data == "bind":
            await query.message.reply_text(
                "独立品牌机器人是可选项。平时直接用 @"
                f"{context.bot.username or 'zhizhusp_bot'} 发卡即可。\n\n"
                "如要自己的机器人：\n1. 打开 @BotFather\n2. 发送 /newbot\n3. 把 Token 发到本对话"
            )
            return
        if data == "status":
            await cmd_start(update, context)
            return
        if data == "pay_stars":
            if is_staff(query.from_user.id):
                await query.message.reply_text("管理员账号免费，不用付费。")
                return
            await _create_stars(query, context, tenant, db)
            return
        if data == "pay_usdt":
            if is_staff(query.from_user.id):
                await query.message.reply_text("管理员账号免费，不用付费。")
                return
            await _create_usdt(query, tenant, db)
            return
        if data == "info":
            return
    finally:
        db.close()


async def _create_stars(query, context, tenant: Tenant, db) -> None:
    if open_order(db, tenant.id):
        await query.message.reply_text("你已有一笔待支付订单，请先完成或等待过期。")
        return
    payload = f"stars:{tenant.id}:{new_code()}"
    price = stars_price(db)
    order = Order(
        public_code=new_code(),
        tenant_id=tenant.id,
        rail="stars",
        plan=tenant.plan or "pro",
        period_days=30,
        amount=price,
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
        prices=[LabeledPrice("30天", price)],
        subscription_period=2592000,
    )


async def _create_usdt(query, tenant: Tenant, db) -> None:
    addr = _pay_address(db)
    if not addr:
        await query.message.reply_text("平台尚未配置 USDT 收款地址，请用 Stars 月费。")
        return
    if open_order(db, tenant.id):
        await query.message.reply_text("你已有一笔待支付订单，请先完成或等待过期。")
        return
    code = new_code()
    url = f"{PUBLIC_BASE_URL}/pay/usdt/{code}"
    yearly = usdt_price(db)
    order = Order(
        public_code=code,
        tenant_id=tenant.id,
        rail="usdt",
        plan=tenant.plan or "pro",
        period_days=365,
        amount=yearly,
        currency="USDT",
        chain=USDT_CHAIN,
        pay_url=url,
        pay_address=addr,
        status="pending",
        expires_at=utcnow() + timedelta(minutes=20),
    )
    db.add(order)
    db.commit()
    await query.message.reply_text(
        f"已创建年付订单 {code}\n金额：{yearly:g} USDT（{USDT_CHAIN}）\n20 分钟内有效。\n{url}",
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
        if not tenant.trial_ends_at and not is_staff(update.effective_user.id):
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
            reply_markup=_kb_home(stars_price(db), usdt_price(db)),
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
        if update.effective_user.username:
            ident.username = update.effective_user.username
        db.add(ident)
        db.commit()
        await update.effective_message.reply_text(f"显示名已设为 {ident.display_name}")
    finally:
        db.close()


async def cmd_prices(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_session()
    try:
        addr = _pay_address(db) or "未设置"
        await update.effective_message.reply_text(
            f"Stars 月费：{stars_price(db)}⭐\n"
            f"USDT 年付：{usdt_price(db):g}\n"
            f"收款地址：{addr}"
        )
    finally:
        db.close()


async def cmd_setprice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_user.id):
        await update.effective_message.reply_text("只有平台创建者可以改价。先在 Railway 填 ADMIN_TG_IDS。")
        return
    if len(context.args) < 2:
        await update.effective_message.reply_text(
            "用法：\n/setprice stars 500\n/setprice usdt 99\n/prices 查看当前价格"
        )
        return
    kind = context.args[0].lower()
    raw = context.args[1]
    db = get_session()
    try:
        if kind in {"stars", "star", "xtr"}:
            try:
                value = int(float(raw))
            except ValueError:
                await update.effective_message.reply_text("Stars 必须是整数，例如 /setprice stars 300")
                return
            if value < 1:
                await update.effective_message.reply_text("Stars 至少 1")
                return
            set_setting(db, "stars_monthly", str(value))
            await update.effective_message.reply_text(
                f"Stars 月费已改为 {value}⭐，新订单立即生效。",
                reply_markup=_kb_home(value, usdt_price(db)),
            )
            return
        if kind in {"usdt", "u", "year"}:
            try:
                value = float(raw)
            except ValueError:
                await update.effective_message.reply_text("USDT 必须是数字，例如 /setprice usdt 79")
                return
            if value <= 0:
                await update.effective_message.reply_text("USDT 必须大于 0")
                return
            set_setting(db, "usdt_yearly", f"{value:g}")
            await update.effective_message.reply_text(
                f"USDT 年付已改为 {value:g}，新订单立即生效。",
                reply_markup=_kb_home(stars_price(db), value),
            )
            return
        await update.effective_message.reply_text("只能改 stars 或 usdt。")
    finally:
        db.close()


async def cmd_setaddr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_user.id):
        await update.effective_message.reply_text("只有平台创建者可以改收款地址。")
        return
    if not context.args:
        await update.effective_message.reply_text("用法：/setaddr 你的TRC20地址")
        return
    addr = context.args[0].strip()
    db = get_session()
    try:
        set_setting(db, "usdt_address", addr)
        await update.effective_message.reply_text(f"USDT 收款地址已改为：{addr}")
    finally:
        db.close()


async def cmd_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_user.id):
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
    app.add_handler(CommandHandler("prices", cmd_prices))
    app.add_handler(CommandHandler("setprice", cmd_setprice))
    app.add_handler(CommandHandler("setaddr", cmd_setaddr))
    app.add_handler(InlineQueryHandler(on_inline))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(PreCheckoutQueryHandler(on_precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, on_successful_payment))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_token))
    return app
