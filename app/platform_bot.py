from __future__ import annotations

import json
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
    WebAppInfo,
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

from app.config import ADMIN_TG_IDS, PUBLIC_BASE_URL, USDT_ADDRESS, USDT_CHAIN, WEBHOOK_BASE_URL, WEBHOOK_SECRET
from app.crypto_token import encrypt_token
from app.db import get_session
from app.models import Identity, Order, Tenant, utcnow
from app.plans import PLANS, clone_on, plan_stars, plan_usdt, price_board, set_clone
from app.services import (
    activate_order,
    add_event,
    find_paid_identity,
    get_or_create_tenant,
    get_setting,
    new_code,
    open_order,
    parse_username,
    save_paid_profile,
    set_setting,
    tenant_usable,
)
from app.verify import card_kb, card_text, share_url

TOKEN_RE = __import__("re").compile(r"^\d{6,}:[A-Za-z0-9_-]{20,}$")
ADMIN_HELP = (
    "管理员命令\n\n"
    "/admin  本说明\n"
    "/prices  查看套餐价格\n"
    "/setprice half|quarter|year|life stars|usdt 金额\n"
    "  例：/setprice year stars 800\n"
    "/setaddr TRC20地址\n"
    "/confirm VH-XXXXXX [txid]\n"
    "/clone on 或 /clone off\n"
    "/status  查看自己状态"
)


def _is_admin(user_id: int) -> bool:
    return bool(ADMIN_TG_IDS) and user_id in ADMIN_TG_IDS


def _pay_address(db) -> str:
    return get_setting(db, "usdt_address", USDT_ADDRESS)


def _bot(context) -> str:
    return context.bot.username or "zhizhusp_bot"


def _mini() -> str:
    base = (PUBLIC_BASE_URL or WEBHOOK_BASE_URL or "").rstrip("/")
    return f"{base}/mini" if base else ""


def _kb_home(db, tenant: Tenant) -> InlineKeyboardMarkup:
    paid = tenant_usable(tenant)
    mini = _mini()
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton("查询登记", callback_data="ask_lookup")],
    ]
    if mini.startswith("https://"):
        rows.append([InlineKeyboardButton("开通套餐", web_app=WebAppInfo(url=mini))])
    else:
        rows.append(
            [
                InlineKeyboardButton("半月", callback_data="plan:half"),
                InlineKeyboardButton("季度", callback_data="plan:quarter"),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton("一年", callback_data="plan:year"),
                InlineKeyboardButton("永久", callback_data="plan:life"),
            ]
        )
    if paid:
        rows.append([InlineKeyboardButton("我的登记", callback_data="edit")])
    rows.append([InlineKeyboardButton("使用说明", callback_data="guide")])
    if _is_admin(tenant.owner_tg_id):
        rows.append([InlineKeyboardButton("管理员", callback_data="admin")])
    return InlineKeyboardMarkup(rows)


def _kb_plan(db, key: str) -> InlineKeyboardMarkup:
    label = PLANS[key]["label"]
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(f"{label} {plan_stars(db, key)}⭐", callback_data=f"stars:{key}"),
                InlineKeyboardButton(f"{label} {plan_usdt(db, key):g}U", callback_data=f"usdt:{key}"),
            ],
            [InlineKeyboardButton("返回", callback_data="status")],
        ]
    )


async def _send_lookup(message, db, name: str, bot_name: str) -> None:
    if not name:
        await message.reply_text("请发送对方用户名，例如 @username")
        return
    ident = find_paid_identity(db, name)
    if not ident:
        await message.reply_text(f"查询结果\n\n@{name} 暂无官方登记。")
        return
    tenant = db.get(Tenant, ident.tenant_id)
    url = share_url(bot_name, tenant.id) if tenant else ""
    await message.reply_text(
        card_text(ident, bot_username=bot_name),
        reply_markup=card_kb(ident, share_url=url, bot_username=bot_name),
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("wait", None)
    db = get_session()
    try:
        user = update.effective_user
        tenant = get_or_create_tenant(db, user.id)
        payload = (context.args[0] if context.args else "").strip()
        if payload.startswith("q") and parse_username(payload[1:]):
            await _send_lookup(update.effective_message, db, parse_username(payload[1:]), _bot(context))
            return
        paid = tenant_usable(tenant)
        if paid:
            save_paid_profile(db, tenant, user)
            text = (
                "蜘蛛 · 官方身份核验\n\n"
                f"登记已开通至 {tenant.paid_until or '管理员'}\n"
                "点下方按钮查询、改资料或续费。"
            )
        else:
            text = (
                "蜘蛛 · 官方身份核验\n\n"
                "查询：点「查询登记」，再发送对方 @用户名\n"
                "开通：点「开通套餐」进小程序付费\n"
                "登记：付费成功后按提示保存姓名与账号"
            )
        if payload in {"q", "ask"}:
            context.user_data["wait"] = "lookup"
            text += "\n\n直接发送要查询的 @用户名。"
        await update.effective_message.reply_text(text, reply_markup=_kb_home(db, tenant))
    finally:
        db.close()


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.args = []
    await cmd_start(update, context)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "使用说明\n\n"
        "1. 查询登记：点按钮或直接发 @用户名\n"
        "2. 任意对话输入 @"
        f"{_bot(context)} 加空格也可进入查询\n"
        "3. 开通套餐：点左下角菜单或首页「开通套餐」\n"
        "4. 开通后可保存自己的官方资料"
    )


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_user.id):
        await update.effective_message.reply_text("仅管理员可用。")
        return
    db = get_session()
    try:
        await update.effective_message.reply_text(ADMIN_HELP + "\n\n" + price_board(db))
    finally:
        db.close()


async def on_inline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.inline_query
    name = parse_username(q.query or "")
    bot_name = _bot(context)
    param = f"q_{name}" if name else "ask"
    start = f"https://t.me/{bot_name}?start={param}"
    title = f"查询 @{name}" if name else "蜘蛛官方核验"
    body = f"正在查询 @{name}" if name else "点击下方按钮，在蜘蛛中发送要查询的用户名。"
    await q.answer(
        [
            InlineQueryResultArticle(
                id=(q.id or "r1")[:64],
                title=title,
                description="进入机器人查看官方登记",
                input_message_content=InputTextMessageContent(body),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("打开查询", url=start)]]),
            )
        ],
        cache_time=0,
        is_personal=True,
    )


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
        if data == "ask_lookup":
            context.user_data["wait"] = "lookup"
            await query.message.reply_text("请发送要查询的用户名，例如 @username")
            return
        if data == "guide":
            await cmd_help(update, context)
            return
        if data == "admin":
            await cmd_admin(update, context)
            return
        if data == "edit":
            if not tenant_usable(tenant):
                await query.message.reply_text("开通后才能保存登记资料。")
                return
            await query.message.reply_text(
                "修改登记\n/setid  数字ID\n/setname  显示名\n/setalert  弹窗\n/setcard  身份卡"
            )
            return
        if data.startswith("plan:"):
            key = data.split(":", 1)[1]
            if key in PLANS:
                meta = PLANS[key]
                await query.message.reply_text(
                    f"{meta['label']} · {plan_stars(db, key)}⭐ 或 {plan_usdt(db, key):g} USDT",
                    reply_markup=_kb_plan(db, key),
                )
            return
        if data.startswith("stars:"):
            await _pay_stars(query.from_user.id, query.message, context, tenant, db, data.split(":", 1)[1])
            return
        if data.startswith("usdt:"):
            await _pay_usdt(query.message, tenant, db, data.split(":", 1)[1])
            return
    finally:
        db.close()


async def _pay_stars(chat_id, message, context, tenant: Tenant, db, key: str) -> None:
    if key not in PLANS:
        key = "year"
    if open_order(db, tenant.id):
        await message.reply_text("已有待支付订单，请先完成或等待过期。")
        return
    price = plan_stars(db, key)
    payload = f"stars:{key}:{tenant.id}:{new_code()}"
    db.add(
        Order(
            public_code=new_code(),
            tenant_id=tenant.id,
            rail="stars",
            plan=key,
            period_days=PLANS[key]["days"],
            amount=price,
            currency="XTR",
            status="pending",
            payload=payload,
            expires_at=utcnow() + timedelta(hours=24),
        )
    )
    db.commit()
    await context.bot.send_invoice(
        chat_id=chat_id,
        title=f"蜘蛛核验·{PLANS[key]['label']}",
        description="开通后可保存官方资料",
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(PLANS[key]["label"], price)],
    )


async def _pay_usdt(message, tenant: Tenant, db, key: str) -> None:
    if key not in PLANS:
        key = "year"
    addr = _pay_address(db)
    if not addr:
        await message.reply_text("尚未配置 USDT 地址，请用 Stars。")
        return
    if open_order(db, tenant.id):
        await message.reply_text("已有待支付订单，请先完成或等待过期。")
        return
    code = new_code()
    url = f"{PUBLIC_BASE_URL}/pay/usdt/{code}"
    amount = plan_usdt(db, key)
    db.add(
        Order(
            public_code=code,
            tenant_id=tenant.id,
            rail="usdt",
            plan=key,
            period_days=PLANS[key]["days"],
            amount=amount,
            currency="USDT",
            chain=USDT_CHAIN,
            pay_url=url,
            pay_address=addr,
            status="pending",
            expires_at=utcnow() + timedelta(minutes=20),
        )
    )
    db.commit()
    await message.reply_text(
        f"{PLANS[key]['label']}  {amount:g} USDT\n订单 {code}\n20 分钟内有效",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("打开收银台", url=url)]]),
    )


async def on_webapp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    raw = update.effective_message.web_app_data.data if update.effective_message.web_app_data else ""
    try:
        data = json.loads(raw)
    except Exception:
        await update.effective_message.reply_text("小程序数据无效，请重试。")
        return
    key = str(data.get("plan") or "year")
    rail = str(data.get("rail") or "stars")
    db = get_session()
    try:
        tenant = get_or_create_tenant(db, update.effective_user.id)
        if rail == "usdt":
            await _pay_usdt(update.effective_message, tenant, db, key)
        else:
            await _pay_stars(update.effective_user.id, update.effective_message, context, tenant, db, key)
    finally:
        db.close()


async def on_precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.pre_checkout_query
    db = get_session()
    try:
        order = db.scalar(select(Order).where(Order.payload == q.invoice_payload))
        if not order or order.status != "pending" or int(order.amount) != q.total_amount:
            await q.answer(ok=False, error_message="订单无效")
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
            await update.message.reply_text("付款已到，订单未找到。")
            return
        if order.telegram_charge_id:
            await update.message.reply_text("这笔已开通。")
            return
        order.telegram_charge_id = pay.telegram_payment_charge_id
        add_event(db, order, "paid", "stars_successful_payment")
        tenant = activate_order(db, order)
        save_paid_profile(db, tenant, update.effective_user)
        await update.message.reply_text(
            f"已开通{PLANS.get(order.plan, {}).get('label', '')}至 {tenant.paid_until}\n点「我的登记」补充资料。"
        )
    finally:
        db.close()


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message and update.message.web_app_data:
        await on_webapp(update, context)
        return
    text = (update.message.text or "").strip()
    if TOKEN_RE.match(text):
        await on_token(update, context)
        return
    name = parse_username(text)
    if not name:
        if context.user_data.get("wait") == "lookup" or "核验" in text:
            await update.effective_message.reply_text("请发送用户名，例如 @username")
        return
    context.user_data.pop("wait", None)
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
        if not clone_on(db):
            await update.effective_message.reply_text("克隆未开启。")
            return
        if not tenant_usable(tenant):
            await update.effective_message.reply_text("请先开通套餐再发送 Token。")
            return
        async with httpx.AsyncClient(timeout=20) as client:
            data = (await client.get(f"https://api.telegram.org/bot{text}/getMe")).json()
        if not data.get("ok"):
            await update.effective_message.reply_text("Token 无效。")
            return
        me = data["result"]
        taken = db.scalar(select(Tenant).where(Tenant.bot_id == me["id"], Tenant.id != tenant.id))
        if taken:
            await update.effective_message.reply_text("该机器人已被绑定。")
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
        await update.effective_message.reply_text(f"已克隆 @{tenant.bot_username}")
    finally:
        db.close()


async def _need_paid(update, db):
    tenant = get_or_create_tenant(db, update.effective_user.id)
    if not tenant_usable(tenant):
        await update.effective_message.reply_text("开通后才能保存登记。")
        return None, None
    return tenant, tenant.identity or Identity(tenant_id=tenant.id)


async def cmd_setid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_session()
    try:
        tenant, ident = await _need_paid(update, db)
        if not ident:
            return
        if not context.args or not context.args[0].isdigit():
            await update.effective_message.reply_text("用法：/setid 数字ID")
            return
        ident.official_user_id = int(context.args[0])
        db.add(ident)
        db.commit()
        await update.effective_message.reply_text("登记已更新。")
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
        await update.effective_message.reply_text("登记已更新。")
    finally:
        db.close()


async def cmd_setalert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_session()
    try:
        tenant, ident = await _need_paid(update, db)
        if not ident:
            return
        if not context.args:
            await update.effective_message.reply_text("用法：/setalert 文案")
            return
        ident.alert_text = " ".join(context.args)[:200]
        db.add(ident)
        db.commit()
        await update.effective_message.reply_text("登记已更新。")
    finally:
        db.close()


async def cmd_setcard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_session()
    try:
        tenant, ident = await _need_paid(update, db)
        if not ident:
            return
        if not context.args:
            await update.effective_message.reply_text("用法：/setcard 正文")
            return
        ident.card_text = " ".join(context.args)
        db.add(ident)
        db.commit()
        await update.effective_message.reply_text("登记已更新。")
    finally:
        db.close()


async def cmd_prices(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_session()
    try:
        await update.effective_message.reply_text(price_board(db) + f"\n地址：{_pay_address(db) or '未设'}")
    finally:
        db.close()


async def cmd_setprice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_user.id):
        return
    if len(context.args) < 3:
        await update.effective_message.reply_text("用法：/setprice year stars 800")
        return
    key, rail, raw = context.args[0].lower(), context.args[1].lower(), context.args[2]
    if key not in PLANS:
        await update.effective_message.reply_text("套餐：half / quarter / year / life")
        return
    db = get_session()
    try:
        if rail in {"stars", "star", "xtr"}:
            set_setting(db, f"stars_{key}", str(int(float(raw))))
        elif rail in {"usdt", "u"}:
            set_setting(db, f"usdt_{key}", f"{float(raw):g}")
        else:
            await update.effective_message.reply_text("通道：stars 或 usdt")
            return
        await update.effective_message.reply_text(price_board(db))
    finally:
        db.close()


async def cmd_clone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_user.id):
        return
    db = get_session()
    try:
        if not context.args or context.args[0].lower() not in {"on", "off", "开", "关"}:
            await update.effective_message.reply_text(f"克隆：{'开' if clone_on(db) else '关'}\n/clone on 或 off")
            return
        on = context.args[0].lower() in {"on", "开"}
        set_clone(db, on)
        await update.effective_message.reply_text("克隆已开启" if on else "克隆已关闭")
    finally:
        db.close()


async def cmd_setaddr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_user.id) or not context.args:
        return
    db = get_session()
    try:
        set_setting(db, "usdt_address", context.args[0].strip())
        await update.effective_message.reply_text("地址已更新。")
    finally:
        db.close()


async def cmd_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_user.id) or not context.args:
        return
    db = get_session()
    try:
        order = db.scalar(select(Order).where(Order.public_code == context.args[0].upper()))
        if not order:
            await update.effective_message.reply_text("订单不存在")
            return
        if order.status in {"active", "paid"}:
            await update.effective_message.reply_text("已开通")
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
    for name, fn in [
        ("start", cmd_start),
        ("status", cmd_status),
        ("help", cmd_help),
        ("admin", cmd_admin),
        ("setid", cmd_setid),
        ("setname", cmd_setname),
        ("setalert", cmd_setalert),
        ("setcard", cmd_setcard),
        ("confirm", cmd_confirm),
        ("prices", cmd_prices),
        ("setprice", cmd_setprice),
        ("setaddr", cmd_setaddr),
        ("clone", cmd_clone),
    ]:
        app.add_handler(CommandHandler(name, fn))
    app.add_handler(InlineQueryHandler(on_inline))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(PreCheckoutQueryHandler(on_precheckout))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, on_webapp))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, on_successful_payment))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return app
