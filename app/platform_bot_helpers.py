from __future__ import annotations

import json
from datetime import timedelta

import httpx
from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Update, WebAppInfo
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, InlineQueryHandler, MessageHandler, PreCheckoutQueryHandler, filters

from app.brand import brand_name, brand_title, bot_username as brand_bot
from app.config import ADMIN_TG_IDS, PUBLIC_BASE_URL, USDT_ADDRESS, USDT_CHAIN, WEBHOOK_BASE_URL
from app.crypto_token import encrypt_token
from app.db import get_session
from app.entry import deny_message
from app.home import render_help, render_start
from app.inline_query import on_inline
from app.models import Identity, Order, Tenant, utcnow
from app.plans import PLANS, clone_on, plan_stars, plan_usdt, price_board, set_clone
from app.services import activate_order, add_admin_audit, add_event, find_paid_by_tg_id, fmt_until, get_or_create_tenant, get_setting, new_code, open_order, parse_username, resolve_paid_identity, save_paid_profile, set_setting, tenant_usable, unique_usdt_amount
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
