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
    find_paid_identity,
    get_or_create_tenant,
    get_setting,
    is_staff,
    new_code,
    open_order,
    parse_username,
    save_paid_profile,
    set_setting,
    stars_price,
    tenant_usable,
    usdt_price,
)
from app.verify import card_kb, card_text, share_url

TOKEN_RE = __import__("re").compile(r"^\d{6,}:[A-Za-z0-9_-]{20,}$")


def _is_admin(user_id: int) -> bool:
    return bool(ADMIN_TG_IDS) and user_id in ADMIN_TG_IDS


def _pay_address(db) -> str:
    return get_setting(db, "usdt_address", USDT_ADDRESS)


def _bot(context) -> str:
    return context.bot.username or "zhizhusp_bot"


def _kb_home(stars: int, usdt: float, paid: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(f"Stars 月费 {stars}⭐", callback_data="pay_stars"),
            InlineKeyboardButton(f"USDT 年付 {usdt:g}", callback_data="pay_usdt"),
        ],
        [InlineKeyboardButton("我的状态", callback_data="status")],
    ]
    if paid:
        rows.insert(0, [InlineKeyboardButton("修改核验资料", callback_data="edit")])
    return InlineKeyboardMarkup(rows)


async def _send_lookup(message, db, name: str, bot_name: str) -> None:
    if not name:
        await message.reply_text("请发送要核验的用户名，例如 @username")
        return
    ident = find_paid_identity(db, name)
    if not ident:
        await message.reply_text(
            f"未找到已开通的官方登记 @{name}。\n"
            "对方需先充值，并在本机器人里保存资料。"
        )
        return
    tenant = db.get(Tenant, ident.tenant_id)
    url = share_url(bot_name, tenant.id) if tenant else ""
    await message.reply_text(
        card_text(ident, watermark=True, bot_username=bot_name),
        reply_markup=card_kb(ident, share_url=url, bot_username=bot_name),
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_session()
    try:
        user = update.effective_user
        tenant = get_or_create_tenant(db, user.id)
        payload = (context.args[0] if context.args else "").strip()
        if payload.startswith("q"):
            name = parse_username(payload[1:])
            await _send_lookup(update.effective_message, db, name, _bot(context))
            return
        paid = tenant_usable(tenant)
        if paid:
            save_paid_profile(db, tenant, user)
            text = (
                "已开通。你的核验资料保存在本机器人。\n"
                f"已付到：{tenant.paid_until or '管理员'}\n\n"
                "修改资料：\n/setid 数字ID\n/setname 显示名\n/setalert 弹窗文案\n/setcard 身份卡正文"
            )
        else:
            text = (
                "官方身份核验平台\n\n"
                "未充值：在任意对话输入 @"
                f"{_bot(context)} 核验 @用户名\n"
                "点击后会跳进本机器人，按用户名查已充值用户存档的官方资料。\n\n"
                "充值后才能在这里登记自己的官方身份。"
            )
        await update.effective_message.reply_text(
            text, reply_markup=_kb_home(stars_price(db), usdt_price(db), paid)
        )
    finally:
        db.close()


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.args = []
    await cmd_start(update, context)


async def on_inline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.inline_query
    db = get_session()
    try:
        raw = (q.query or "").strip()
        name = parse_username(raw)
        param = f"q_{name}" if name else "q"
        bot_name = _bot(context)
        start = f"https://t.me/{bot_name}?start={param}"
        title = f"查询 @{name}" if name else "打开机器人核验用户名"
        await q.answer(
            [
                InlineQueryResultArticle(
                    id="lookup",
                    title=title,
                    description="跳转到机器人，查已充值用户保存的官方资料",
                    input_message_content=InputTextMessageContent(
                        f"点下方按钮打开机器人查询 {('@' + name) if name else '用户名'}"
                    ),
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("打开机器人查询", url=start)]]
                    ),
                )
            ],
            cache_time=1,
            is_personal=True,
            switch_pm_text="打开机器人查询",
            switch_pm_parameter=param[:64],
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
        if data == "status":
            context.args = []
            await cmd_start(update, context)
            return
        if data == "edit":
            if not tenant_usable(tenant):
                await query.message.reply_text("充值后才能保存核验资料。")
                return
            await query.message.reply_text(
                "修改并保存资料：\n/setid 数字ID\n/setname 显示名\n/setalert 弹窗文案\n/setcard 身份卡正文"
            )
            return
        if data == "pay_stars":
            await _create_stars(query, context, tenant, db)
            return
        if data == "pay_usdt":
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
        title="核验套餐月费",
        description="充值后可在机器人里保存官方资料",
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice("30天", price)],
    )


async def _create_usdt(query, tenant: Tenant, db) -> None:
    addr = _pay_address(db)
    if not addr:
        await query.message.reply_text("平台尚未配置 USDT 收款地址，请用 Stars。")
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
        save_paid_profile(db, tenant, update.effective_user)
        await update.message.reply_text(
            f"已开通至 {tenant.paid_until}\n资料已存入机器人。用 /setid /setname /setalert /setcard 修改。"
        )
    finally:
        db.close()


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or "").strip()
    if TOKEN_RE.match(text):
        await on_token(update, context)
        return
    name = parse_username(text)
    if not name:
        return
    db = get_session()
    try:
        await _send_lookup(update.effective_message, db, name, _bot(context))
    finally:
        db.close()


async def on_token(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or "").strip()
    db = get_session()
    try:
        tenant = get_or_create_tenant(db, update.effective_user.id)
        try:
            await update.message.delete()
        except Exception:
            pass
        if not tenant_usable(tenant):
            await update.effective_message.reply_text("请先充值开通，再发送 Token 克隆。")
            return
        async with httpx.AsyncClient(timeout=20) as client:
            data = (await client.get(f"https://api.telegram.org/bot{text}/getMe")).json()
        if not data.get("ok"):
            await update.effective_message.reply_text("Token 无效。")
            return
        me = data["result"]
        taken = db.scalar(select(Tenant).where(Tenant.bot_id == me["id"], Tenant.id != tenant.id))
        if taken:
            await update.effective_message.reply_text("这个机器人已被绑定。")
            return
        tenant.bot_id = me["id"]
        tenant.bot_username = me.get("username")
        tenant.bot_token_enc = encrypt_token(text)
        db.commit()
        if WEBHOOK_BASE_URL:
            async with httpx.AsyncClient(timeout=20) as client:
                await client.post(
                    f"https://api.telegram.org/bot{text}/setWebhook",
                    json={
                        "url": f"{WEBHOOK_BASE_URL}/wh/t/{tenant.id}",
                        "secret_token": WEBHOOK_SECRET,
                        "allowed_updates": ["message", "callback_query", "inline_query"],
                    },
                )
        await update.effective_message.reply_text(f"已绑定 @{tenant.bot_username}")
    finally:
        db.close()


async def _need_paid(update, db):
    tenant = get_or_create_tenant(db, update.effective_user.id)
    if not tenant_usable(tenant):
        await update.effective_message.reply_text("充值后才能在机器人里保存核验资料。")
        return None, None
    ident = tenant.identity or Identity(tenant_id=tenant.id)
    return tenant, ident


async def cmd_setid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_session()
    try:
        tenant, ident = await _need_paid(update, db)
        if not ident:
            return
        if not context.args or not context.args[0].isdigit():
            await update.effective_message.reply_text("用法：/setid 你的Telegram数字ID")
            return
        ident.official_user_id = int(context.args[0])
        db.add(ident)
        db.commit()
        await update.effective_message.reply_text(f"资料已保存，官方 ID {ident.official_user_id}")
    finally:
        db.close()


async def cmd_setname(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_session()
    try:
        tenant, ident = await _need_paid(update, db)
        if not ident:
            return
        if not context.args:
            await update.effective_message.reply_text("用法：/setname 显示名")
            return
        ident.display_name = " ".join(context.args)
        if update.effective_user.username:
            ident.username = update.effective_user.username
        db.add(ident)
        db.commit()
        await update.effective_message.reply_text(f"资料已保存，显示名 {ident.display_name}")
    finally:
        db.close()


async def cmd_setalert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_session()
    try:
        tenant, ident = await _need_paid(update, db)
        if not ident:
            return
        if not context.args:
            await update.effective_message.reply_text("用法：/setalert 弹窗文案")
            return
        ident.alert_text = " ".join(context.args)[:200]
        db.add(ident)
        db.commit()
        await update.effective_message.reply_text("弹窗文案已保存。")
    finally:
        db.close()


async def cmd_setcard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_session()
    try:
        tenant, ident = await _need_paid(update, db)
        if not ident:
            return
        if not context.args:
            await update.effective_message.reply_text("用法：/setcard 身份卡正文")
            return
        ident.card_text = " ".join(context.args)
        db.add(ident)
        db.commit()
        await update.effective_message.reply_text("身份卡已保存。")
    finally:
        db.close()


async def cmd_prices(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_session()
    try:
        addr = _pay_address(db) or "未设置"
        await update.effective_message.reply_text(
            f"Stars 月费：{stars_price(db)}⭐\nUSDT 年付：{usdt_price(db):g}\n收款地址：{addr}"
        )
    finally:
        db.close()


async def cmd_setprice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_user.id):
        await update.effective_message.reply_text("只有平台创建者可以改价。")
        return
    if len(context.args) < 2:
        await update.effective_message.reply_text("用法：/setprice stars 500 或 /setprice usdt 99")
        return
    kind = context.args[0].lower()
    raw = context.args[1]
    db = get_session()
    try:
        if kind in {"stars", "star", "xtr"}:
            set_setting(db, "stars_monthly", str(int(float(raw))))
            await update.effective_message.reply_text(f"Stars 月费已改为 {int(float(raw))}⭐")
            return
        if kind in {"usdt", "u", "year"}:
            set_setting(db, "usdt_yearly", f"{float(raw):g}")
            await update.effective_message.reply_text(f"USDT 年付已改为 {float(raw):g}")
            return
        await update.effective_message.reply_text("只能改 stars 或 usdt。")
    finally:
        db.close()


async def cmd_setaddr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.effective_message.reply_text("用法：/setaddr TRC20地址")
        return
    db = get_session()
    try:
        set_setting(db, "usdt_address", context.args[0].strip())
        await update.effective_message.reply_text("收款地址已更新。")
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
    app.add_handler(CommandHandler("setalert", cmd_setalert))
    app.add_handler(CommandHandler("setcard", cmd_setcard))
    app.add_handler(CommandHandler("confirm", cmd_confirm))
    app.add_handler(CommandHandler("prices", cmd_prices))
    app.add_handler(CommandHandler("setprice", cmd_setprice))
    app.add_handler(CommandHandler("setaddr", cmd_setaddr))
    app.add_handler(InlineQueryHandler(on_inline))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(PreCheckoutQueryHandler(on_precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, on_successful_payment))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return app
