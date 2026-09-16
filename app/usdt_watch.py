from __future__ import annotations

import asyncio
import logging
import os
from datetime import timedelta
from types import SimpleNamespace

import httpx
from sqlalchemy import select

from app.config import USDT_ADDRESS, USDT_CHAIN
from app.db import get_session
from app.models import Order, Tenant, utcnow
from app.plans import PLANS
from app.services import activate_order, add_event, get_setting, save_paid_profile, set_setting

log = logging.getLogger("zhizhu.usdt")
USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
TRONGRID = "https://api.trongrid.io/v1/accounts/{addr}/transactions/trc20"


def _api_key() -> str:
    return os.getenv("TRONGRID_API_KEY", "")


async def _incoming(address: str) -> list[dict]:
    headers = {}
    key = _api_key()
    if key:
        headers["TRON-PRO-API-KEY"] = key
    params = {"only_to": "true", "limit": 40, "contract_address": USDT_CONTRACT}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(TRONGRID.format(addr=address), params=params, headers=headers)
        data = r.json()
    return list(data.get("data") or [])


def _usdt_amount(row: dict) -> float:
    try:
        return int(row.get("value") or 0) / 1_000_000
    except (TypeError, ValueError):
        return 0.0


async def _profile_from_bot(bot, tg_id: int):
    try:
        chat = await bot.get_chat(tg_id)
    except Exception:
        return SimpleNamespace(id=tg_id, username=None, full_name="")
    name = getattr(chat, "full_name", "") or " ".join(
        x for x in (getattr(chat, "first_name", None), getattr(chat, "last_name", None)) if x
    )
    return SimpleNamespace(id=tg_id, username=getattr(chat, "username", None), full_name=name)


async def remind_expiring(bot) -> None:
    if not bot:
        return
    db = get_session()
    try:
        now = utcnow()
        soon = now + timedelta(days=7)
        rows = list(
            db.scalars(
                select(Tenant).where(
                    Tenant.paid_until.is_not(None),
                    Tenant.paid_until > now,
                    Tenant.paid_until <= soon,
                )
            )
        )
        for tenant in rows:
            key = f"remind:{tenant.id}:{tenant.paid_until.date()}"
            if get_setting(db, key):
                continue
            set_setting(db, key, "1")
            try:
                await bot.send_message(
                    chat_id=tenant.owner_tg_id,
                    text=f"你的官方核验将于 {tenant.paid_until} 到期，点左下角「开通套餐」续费。",
                )
            except Exception as exc:
                log.warning("remind failed %s", exc)
    finally:
        db.close()


async def check_once(bot=None) -> int:
    if (USDT_CHAIN or "trc20").lower() not in {"trc20", "trx", "tron"}:
        return 0
    db = get_session()
    activated = 0
    try:
        addr = get_setting(db, "usdt_address", USDT_ADDRESS).strip()
        if not addr:
            return 0
        pending = list(
            db.scalars(
                select(Order).where(
                    Order.rail == "usdt",
                    Order.status.in_(("pending", "confirming", "draft")),
                )
            )
        )
        now = utcnow()
        for order in pending:
            if order.expires_at and order.expires_at < now:
                add_event(db, order, "expired", "timeout")
        db.commit()
        pending = [o for o in pending if o.status in {"pending", "confirming", "draft"}]
        if not pending:
            return 0
        txs = await _incoming(addr)
        used = {row.txid for row in db.scalars(select(Order).where(Order.txid.is_not(None)))}
        for tx in txs:
            txid = tx.get("transaction_id") or ""
            if not txid or txid in used:
                continue
            to_addr = (tx.get("to") or "").strip()
            if to_addr and to_addr != addr:
                continue
            paid = _usdt_amount(tx)
            if paid <= 0:
                continue
            ts = int(tx.get("block_timestamp") or 0) / 1000
            match = None
            for order in pending:
                if abs(float(order.amount) - paid) > 0.001:
                    continue
                created = order.created_at.timestamp() if order.created_at else 0
                if ts and created and ts + 120 < created:
                    continue
                match = order
                break
            if not match:
                continue
            match.txid = txid
            add_event(db, match, "paid", "trongrid_auto")
            tenant = activate_order(db, match)
            user = await _profile_from_bot(bot, tenant.owner_tg_id) if bot else SimpleNamespace(
                id=tenant.owner_tg_id, username=None, full_name=""
            )
            save_paid_profile(db, tenant, user)
            pending.remove(match)
            used.add(txid)
            activated += 1
            if bot and tenant:
                label = PLANS.get(match.plan, {}).get("label", match.plan)
                uname = f"@{user.username}" if user.username else "未设用户名"
                try:
                    await bot.send_message(
                        chat_id=tenant.owner_tg_id,
                        text=(
                            f"已收到 {paid:g} USDT，{label}已开通至 {tenant.paid_until}\n\n"
                            f"已按你的 Telegram 账号生成登记\n"
                            f"账号 {uname}\nID {tenant.owner_tg_id}"
                        ),
                    )
                except Exception as exc:
                    log.warning("notify failed %s", exc)
        return activated
    finally:
        db.close()


async def watch_loop(bot) -> None:
    await asyncio.sleep(8)
    ticks = 0
    while True:
        try:
            n = await check_once(bot)
            if n:
                log.info("auto-activated %s usdt orders", n)
            ticks += 1
            if ticks % 24 == 1:
                await remind_expiring(bot)
        except Exception:
            log.exception("usdt watch")
        await asyncio.sleep(25)
