from __future__ import annotations

import json
from datetime import timedelta

import httpx
from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Update, WebAppInfo
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, InlineQueryHandler, MessageHandler, PreCheckoutQueryHandler, filters

from app.brand import brand_name, brand_title, bot_username as brand_bot
from app.config import ADMIN_TG_IDS, PUBLIC_BASE_URL, USDT_ADDRESS, USDT_CHAIN, WEBHOOK_BASE_URL, WEBHOOK_SECRET
from app.crypto_token import encrypt_token
from app.db import get_session
from app.inline_query import on_inline
from app.models import Identity, Order, Tenant, utcnow
from app.plans import PLANS, clone_on, plan_stars, plan_usdt, price_board, set_clone
from app.services import activate_order, add_event, find_paid_by_tg_id, fmt_until, get_or_create_tenant, get_setting, new_code, open_order, parse_username, resolve_paid_identity, save_paid_profile, set_setting, tenant_usable
from app.verify import card_kb, card_text, promo_text, share_url

TOKEN_RE = __import__('re').compile(r'^\d{6,}:[A-Za-z0-9_-]{20,}$')


def _is_admin(user_id: int) -> bool:
    return bool(ADMIN_TG_IDS) and user_id in ADMIN_TG_IDS


def _pay_address(db) -> str:
    return get_setting(db, 'usdt_address', USDT_ADDRESS)


def _bot(context) -> str:
    return (context.bot.username or brand_bot()).lstrip('@')


def _mini() -> str:
    base = (PUBLIC_BASE_URL or WEBHOOK_BASE_URL or '').rstrip('/')
    return f'{base}/mini' if base else ''


def _kb_admin(db) -> InlineKeyboardMarkup:
    clone = '克隆：开' if clone_on(db) else '克隆：关'
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('当前价格', callback_data='adm:prices')],
        [InlineKeyboardButton('修改价格', callback_data='adm:price')],
        [InlineKeyboardButton('修改收款地址', callback_data='adm:addr')],
        [InlineKeyboardButton('确认 USDT 订单', callback_data='adm:confirm')],
        [InlineKeyboardButton(clone, callback_data='adm:clone')],
        [InlineKeyboardButton('返回首页', callback_data='status')],
    ])


def _kb_home(db, tenant: Tenant) -> InlineKeyboardMarkup:
    mini = _mini()
    rows = [[InlineKeyboardButton('查询登记', callback_data='ask_lookup')]]
    if mini.startswith('https://'):
        rows.append([InlineKeyboardButton('小程序', web_app=WebAppInfo(url=mini))])
    if _is_admin(tenant.owner_tg_id):
        rows.append([InlineKeyboardButton('管理员', callback_data='admin')])
    return InlineKeyboardMarkup(rows)


async def _send_lookup(message, db, name: str, bot_name: str, bot=None, user=None) -> None:
    if not name:
        await message.reply_text('请发送对方用户名，例如 @username')
        return
    ident = await resolve_paid_identity(db, name, bot)
    if not ident and user:
        tenant = get_or_create_tenant(db, user.id)
        mine = find_paid_by_tg_id(db, user.id)
        my_name = (getattr(user, 'username', None) or '').lstrip('@')
        if mine and tenant_usable(tenant) and my_name and my_name.lower() == name.lower():
            mine.username = my_name
            db.commit()
            ident = mine
    if not ident:
        await message.reply_text(promo_text(bot_name, name), reply_markup=card_kb(username=name, bot_username=bot_name))
        return
    tenant = db.get(Tenant, ident.tenant_id)
    url = share_url(bot_name, tenant.id) if tenant else ''
    await message.reply_text(card_text(ident, bot_username=bot_name), reply_markup=card_kb(ident, share_url=url, bot_username=bot_name))


async def _show_admin(message, db) -> None:
    addr = _pay_address(db) or '未设'
    pending = list(db.scalars(select(Order).where(Order.rail == 'usdt', Order.status.in_(('pending', 'confirming'))).order_by(Order.id.desc()).limit(8)))
    lines = [f'管理后台\n\n{price_board(db)}', f'收款地址：{addr}', '', '待确认订单（订单号即 VH- 开头）']
    lines.extend([f'{o.public_code}  {float(o.amount):g}U  {o.status}' for o in pending] or ['暂无待确认 USDT 订单'])
    await message.reply_text('\n'.join(lines), reply_markup=_kb_admin(db))


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop('wait', None)
    db = get_session()
    try:
        user = update.effective_user
        tenant = get_or_create_tenant(db, user.id)
        payload = (context.args[0] if context.args else '').strip()
        if payload.startswith('q') and parse_username(payload[1:]):
            await _send_lookup(update.effective_message, db, parse_username(payload[1:]), _bot(context), bot=context.bot, user=user)
            return
        if tenant_usable(tenant):
            ident = save_paid_profile(db, tenant, user)
            uname = f'@{ident.username}' if ident.username else '未同步用户名'
            text = f"{brand_name()} · {brand_title()}\n\n登记已开通至 {fmt_until(tenant.paid_until) or '管理员'}\n当前资料：{uname}  ID {ident.official_user_id or user.id}\n改资料请点左下角「小程序」。"
        else:
            text = f"{brand_name()} · {brand_title()}\n\n查询：点「查询登记」，再发送 @用户名\n开通与改资料：左下角「小程序」"
        if payload in {'q', 'ask'}:
            context.user_data['wait'] = 'lookup'
            text += '\n\n直接发送要查询的 @用户名。'
        await update.effective_message.reply_text(text, reply_markup=_kb_home(db, tenant))
    finally:
        db.close()


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.args = []
    await cmd_start(update, context)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(f"使用说明\n\n1. 群里输入 @{_bot(context)} 加用户名\n2. 开通与改资料：左下角「小程序」\n3. 开通后自动生成登记")


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_user.id):
        await update.effective_message.reply_text('仅管理员可用。')
        return
    db = get_session()
    try:
        await _show_admin(update.effective_message, db)
    finally:
        db.close()


async def cmd_paid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_user.id):
        return
    db = get_session()
    try:
        rows = list(db.scalars(select(Tenant).order_by(Tenant.id.desc()).limit(40)))
        lines = ['已开通用户']
        for tenant in rows:
            if not tenant_usable(tenant):
                continue
            ident = tenant.identity
            uname = f'@{ident.username}' if ident and ident.username else '无用户名'
            lines.append(f'#{tenant.id}  TG {tenant.owner_tg_id}  {uname}  至 {fmt_until(tenant.paid_until) or "-"}')
        if len(lines) == 1:
            lines.append('暂无')
        lines.append('\n补登记：/bind Q_7ge')
        await update.effective_message.reply_text('\n'.join(lines))
    finally:
        db.close()


async def cmd_bind(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.effective_message.reply_text('用法：/bind 用户名\n或 /bind 用户名 电报ID')
        return
    name = parse_username(context.args[0]) or context.args[0].lstrip('@')
    tg_id = 0
    if len(context.args) > 1 and context.args[1].lstrip('-').isdigit():
        tg_id = int(context.args[1])
    db = get_session()
    try:
        if not tg_id:
            try:
                chat = await context.bot.get_chat('@' + name)
                tg_id = chat.id
            except Exception as exc:
                await update.effective_message.reply_text(f'电报查不到 @{name}\n{exc}\n改用 /bind {name} 电报ID')
                return
        tenant = db.scalar(select(Tenant).where(Tenant.owner_tg_id == tg_id))
        if not tenant:
            ident = db.scalar(select(Identity).where(Identity.official_user_id == tg_id))
            tenant = db.get(Tenant, ident.tenant_id) if ident else None
        if not tenant:
            await update.effective_message.reply_text(f'库里没有 TG {tg_id} 的开通记录。先发 /paid 看列表。')
            return
        ident = tenant.identity or Identity(tenant_id=tenant.id)
        ident.username = name
        ident.official_user_id = ident.official_user_id or tg_id
        if not ident.display_name:
            ident.display_name = name
        db.add(ident)
        db.commit()
        await update.effective_message.reply_text(
            f'已补登记 @{name}\nTG {tenant.owner_tg_id}\n开通至 {fmt_until(tenant.paid_until) or "-"}'
        )
    finally:
        db.close()


async def _admin_cb(query, context, data: str, db) -> bool:
    if not data.startswith('adm:') and data != 'admin':
        return False
    if not _is_admin(query.from_user.id):
        await query.message.reply_text('仅管理员可用。')
        return True
    if data in {'admin', 'adm:home', 'adm:prices'}:
        await _show_admin(query.message, db)
        return True
    if data == 'adm:price':
        await query.message.reply_text('选择要改价的套餐', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('一年', callback_data='adm:pk:year')],[InlineKeyboardButton('返回后台', callback_data='admin')]]))
        return True
    if data.startswith('adm:pk:'):
        key = data.split(':')[2]
        await query.message.reply_text(
            f"{PLANS[key]['label']} 现价 {plan_stars(db, key)}⭐ / {plan_usdt(db, key):g} U",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Stars', callback_data=f'adm:pr:{key}:stars'), InlineKeyboardButton('USDT', callback_data=f'adm:pr:{key}:usdt')],[InlineKeyboardButton('返回', callback_data='adm:price')]]),
        )
        return True
    if data.startswith('adm:pr:'):
        _, _, key, rail = data.split(':')
        context.user_data['wait'] = f'admin_price:{key}:{rail}'
        await query.message.reply_text(f"发送新的 {PLANS[key]['label']} {'⭐' if rail=='stars' else 'USDT'} 价格")
        return True
    if data == 'adm:addr':
        context.user_data['wait'] = 'admin_addr'
        await query.message.reply_text(f"当前地址：{_pay_address(db) or '未设'}\n发送新的 TRC20 地址。")
        return True
    if data == 'adm:confirm':
        context.user_data['wait'] = 'admin_confirm'
        await query.message.reply_text('发送订单号，例如 VH-XXXXXX。')
        await _show_admin(query.message, db)
        return True
    if data == 'adm:clone':
        on = not clone_on(db)
        set_clone(db, on)
        await query.message.reply_text('克隆已开启' if on else '克隆已关闭', reply_markup=_kb_admin(db))
        return True
    return True


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ''
    db = get_session()
    try:
        tenant = get_or_create_tenant(db, query.from_user.id)
        if await _admin_cb(query, context, data, db):
            return
        if data == 'status':
            context.args = []
            await cmd_start(update, context)
            return
        if data == 'ask_lookup':
            context.user_data['wait'] = 'lookup'
            await query.message.reply_text('请发送要查询的用户名，例如 @username')
            return
        if data.startswith('stars:'):
            await _pay_stars(query.from_user.id, query.message, context, tenant, db, data.split(':', 1)[1])
        elif data.startswith('usdt:'):
            await _pay_usdt(query.message, tenant, db, data.split(':', 1)[1])
    finally:
        db.close()


async def _pay_stars(chat_id, message, context, tenant: Tenant, db, key: str) -> None:
    if key not in PLANS:
        key = 'year'
    if open_order(db, tenant.id):
        await message.reply_text('已有待支付订单。')
        return
    price = plan_stars(db, key)
    payload = f'stars:{key}:{tenant.id}:{new_code()}'
    db.add(Order(public_code=new_code(), tenant_id=tenant.id, rail='stars', plan=key, period_days=PLANS[key]['days'], amount=price, currency='XTR', status='pending', payload=payload, expires_at=utcnow() + timedelta(hours=24)))
    db.commit()
    await context.bot.send_invoice(chat_id=chat_id, title=f"{brand_name()}·{PLANS[key]['label']}", description='开通后可保存官方资料', payload=payload, provider_token='', currency='XTR', prices=[LabeledPrice(PLANS[key]['label'], price)])


async def _pay_usdt(message, tenant: Tenant, db, key: str) -> None:
    if key not in PLANS:
        key = 'year'
    addr = _pay_address(db)
    if not addr:
        await message.reply_text('尚未配置 USDT 地址')
        return
    if open_order(db, tenant.id):
        await message.reply_text('已有待支付订单。')
        return
    code = new_code()
    amount = plan_usdt(db, key)
    db.add(Order(public_code=code, tenant_id=tenant.id, rail='usdt', plan=key, period_days=PLANS[key]['days'], amount=amount, currency='USDT', chain=USDT_CHAIN, pay_address=addr, status='pending', expires_at=utcnow() + timedelta(minutes=20)))
    db.commit()
    await message.reply_text(f"{PLANS[key]['label']}  {amount:g} USDT\n订单 {code}\n20 分钟内有效")


async def on_webapp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    raw = update.effective_message.web_app_data.data if update.effective_message.web_app_data else ''
    try:
        data = json.loads(raw)
    except Exception:
        await update.effective_message.reply_text('小程序数据无效')
        return
    db = get_session()
    try:
        tenant = get_or_create_tenant(db, update.effective_user.id)
        rail = str(data.get('rail') or 'stars')
        key = str(data.get('plan') or 'year')
        if rail == 'usdt':
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
        if not order or order.status != 'pending' or int(order.amount) != q.total_amount:
            await q.answer(ok=False, error_message='订单无效')
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
            await update.message.reply_text('付款已到，订单未找到')
            return
        if order.telegram_charge_id:
            await update.message.reply_text('这笔已开通')
            return
        order.telegram_charge_id = pay.telegram_payment_charge_id
        add_event(db, order, 'paid', 'stars_successful_payment')
        tenant = activate_order(db, order)
        save_paid_profile(db, tenant, update.effective_user)
        await update.message.reply_text(f"已开通{PLANS.get(order.plan, {}).get('label', '')}至 {fmt_until(tenant.paid_until)}")
    finally:
        db.close()


async def _handle_admin_text(update, context, text: str) -> bool:
    wait = context.user_data.get('wait') or ''
    if not wait.startswith('admin_'):
        return False
    if not _is_admin(update.effective_user.id):
        context.user_data.pop('wait', None)
        return False
    db = get_session()
    try:
        if wait == 'admin_addr':
            addr = text.split()[0]
            if not addr.startswith('T') or len(addr) < 30:
                await update.effective_message.reply_text('请发送 TRC20 地址')
                return True
            set_setting(db, 'usdt_address', addr)
            context.user_data.pop('wait', None)
            await update.effective_message.reply_text(f'收款地址已更新\n{addr}', reply_markup=_kb_admin(db))
            return True
        if wait.startswith('admin_price:'):
            _, key, rail = wait.split(':')
            try:
                value = float(text.replace(',', ''))
            except ValueError:
                await update.effective_message.reply_text('请只发数字')
                return True
            set_setting(db, f"{'stars' if rail=='stars' else 'usdt'}_{key}", str(int(value) if rail=='stars' else f'{value:g}'))
            context.user_data.pop('wait', None)
            await update.effective_message.reply_text(price_board(db), reply_markup=_kb_admin(db))
            return True
        if wait == 'admin_confirm':
            parts = text.split()
            order = db.scalar(select(Order).where(Order.public_code == parts[0].upper()))
            if not order:
                await update.effective_message.reply_text('订单不存在')
                return True
            if len(parts) > 1:
                order.txid = parts[1]
            add_event(db, order, 'paid', 'manual_confirm')
            tenant = activate_order(db, order)
            context.user_data.pop('wait', None)
            await update.effective_message.reply_text(f'{order.public_code} 已开通至 {fmt_until(tenant.paid_until)}', reply_markup=_kb_admin(db))
            return True
        return False
    finally:
        db.close()


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message and update.message.web_app_data:
        await on_webapp(update, context)
        return
    text = (update.message.text or '').strip()
    if await _handle_admin_text(update, context, text):
        return
    if TOKEN_RE.match(text):
        await on_token(update, context)
        return
    name = parse_username(text)
    if not name:
        if context.user_data.get('wait') == 'lookup':
            await update.effective_message.reply_text('请发送用户名，例如 @username')
        return
    context.user_data.pop('wait', None)
    db = get_session()
    try:
        await _send_lookup(update.effective_message, db, name, _bot(context), bot=context.bot, user=update.effective_user)
    finally:
        db.close()


async def on_token(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or '').strip()
    db = get_session()
    try:
        tenant = get_or_create_tenant(db, update.effective_user.id)
        try:
            await update.message.delete()
        except Exception:
            pass
        if not clone_on(db):
            await update.effective_message.reply_text('克隆未开启')
            return
        if not tenant_usable(tenant):
            await update.effective_message.reply_text('请先开通再绑定 Token')
            return
        async with httpx.AsyncClient(timeout=20) as client:
            data = (await client.get(f'https://api.telegram.org/bot{text}/getMe')).json()
        if not data.get('ok'):
            await update.effective_message.reply_text('Token 无效')
            return
        me = data['result']
        tenant.bot_id = me['id']
        tenant.bot_username = me.get('username')
        tenant.bot_token_enc = encrypt_token(text)
        db.commit()
        await update.effective_message.reply_text(f"已克隆 @{tenant.bot_username}")
    finally:
        db.close()


async def cmd_admin_alias(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_admin(update, context)


def build_platform_app(token: str) -> Application:
    app = Application.builder().token(token).updater(None).build()
    for name, fn in [
        ('start', cmd_start), ('status', cmd_status), ('help', cmd_help), ('admin', cmd_admin),
        ('paid', cmd_paid), ('bind', cmd_bind),
        ('confirm', cmd_admin_alias), ('prices', cmd_admin_alias), ('setprice', cmd_admin_alias),
        ('setaddr', cmd_admin_alias), ('clone', cmd_admin_alias),
    ]:
        app.add_handler(CommandHandler(name, fn))
    app.add_handler(InlineQueryHandler(on_inline))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(PreCheckoutQueryHandler(on_precheckout))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, on_webapp))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, on_successful_payment))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return app
