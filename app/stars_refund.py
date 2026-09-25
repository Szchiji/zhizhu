"""Telegram Stars official refund via Bot API refundStarPayment."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import PLATFORM_BOT_TOKEN
from app.models import Order, Tenant

log = logging.getLogger("zhizhu.stars_refund")

TG_API = "https://api.telegram.org"


async def refund_star_payment(
    *,
    user_id: int,
    telegram_payment_charge_id: str,
    bot_token: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """POST refundStarPayment. Returns normalized outcome dict.

    Idempotent: CHARGE_ALREADY_REFUNDED is treated as ok/already=True.
    """
    token = (bot_token or PLATFORM_BOT_TOKEN or "").strip()
    charge = (telegram_payment_charge_id or "").strip()
    if not token:
        return {
            "attempted": False,
            "ok": False,
            "already": False,
            "skipped": True,
            "error": "no_bot_token",
            "description": "未配置 PLATFORM_BOT_TOKEN，仅内部撤销",
        }
    if not user_id or not charge:
        return {
            "attempted": False,
            "ok": False,
            "already": False,
            "skipped": True,
            "error": "missing_charge_or_user",
            "description": "缺少 charge_id 或用户，仅内部撤销",
        }

    url = f"{TG_API}/bot{token}/refundStarPayment"
    payload = {"user_id": int(user_id), "telegram_payment_charge_id": charge}
    owns = client is None
    http = client or httpx.AsyncClient(timeout=20.0)
    try:
        resp = await http.post(url, json=payload)
        data = resp.json() if resp.content else {}
    except Exception as exc:  # noqa: BLE001
        log.warning("refundStarPayment network error: %s", exc)
        return {
            "attempted": True,
            "ok": False,
            "already": False,
            "skipped": False,
            "error": "network",
            "description": str(exc)[:200],
        }
    finally:
        if owns:
            await http.aclose()

    if data.get("ok") is True:
        return {
            "attempted": True,
            "ok": True,
            "already": False,
            "skipped": False,
            "error": "",
            "description": "Telegram Stars 已退款",
        }

    desc = str(data.get("description") or data.get("error") or resp.text or "unknown")[:240]
    upper = desc.upper()
    if "CHARGE_ALREADY_REFUNDED" in upper or "ALREADY_REFUNDED" in upper:
        return {
            "attempted": True,
            "ok": True,
            "already": True,
            "skipped": False,
            "error": "",
            "description": "Telegram 侧已退过款（幂等）",
        }
    log.warning("refundStarPayment failed user=%s charge=%s desc=%s", user_id, charge[:16], desc)
    return {
        "attempted": True,
        "ok": False,
        "already": False,
        "skipped": False,
        "error": "telegram_error",
        "description": desc,
    }


async def refund_stars_for_order(
    order: Order,
    tenant: Tenant | None,
    *,
    bot_token: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Refund Stars for an order when rail=stars and charge_id present."""
    if (order.rail or "").lower() != "stars":
        return {
            "attempted": False,
            "ok": False,
            "already": False,
            "skipped": True,
            "error": "not_stars",
            "description": "非 Stars 订单，跳过官方退款",
        }
    charge = (order.telegram_charge_id or "").strip()
    uid = int(tenant.owner_tg_id) if tenant and tenant.owner_tg_id else 0
    return await refund_star_payment(
        user_id=uid,
        telegram_payment_charge_id=charge,
        bot_token=bot_token,
        client=client,
    )
