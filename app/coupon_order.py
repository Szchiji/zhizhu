from __future__ import annotations

import re
from datetime import timedelta
from types import SimpleNamespace

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import PLATFORM_BOT_TOKEN, USDT_ADDRESS, USDT_CHAIN
from app.coupons import apply_percent, coupon_error, find_coupon, mark_redeemed
from app.db import get_session
from app.entry import deny_json
from app.models import Order, utcnow
from app.plans import ensure_plan_key, plan_info, plan_stars, plan_usdt
from app.services import (
    get_or_create_tenant,
    get_setting,
    new_code,
    save_paid_profile,
    unique_usdt_amount,
)
from app.tg_webapp import require_webapp_user, user_from_init

_SLUG_RE = re.compile(r"(?:\$|invoice/)([A-Za-z0-9\-_=]+)")


def _drop_open_orders(db, tenant_id: int) -> None:
    from app.services import add_event, open_order

    while True:
        order = open_order(db, tenant_id)
        if not order:
            return
        add_event(db, order, "canceled", "replaced_by_new_checkout")
        db.commit()


def _safe_payload(key: str, tenant_id: int) -> str:
    raw_key = re.sub(r"[^A-Za-z0-9]", "", str(key or "year"))[:16] or "year"
    code = re.sub(r"[^A-Za-z0-9]", "", new_code())[:16]
    return f"s{raw_key}_{int(tenant_id)}_{code}"[:128]


async def _tg_json(method: str, payload: dict) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            f"https://api.telegram.org/bot{PLATFORM_BOT_TOKEN}/{method}",
            json=payload,
        )
        try:
            return r.json()
        except Exception:
            return {"ok": False, "description": f"telegram {method} {r.status_code}"}


def remount_mini_order(app) -> None:
    kept = []
    for route in list(app.router.routes):
        path = getattr(route, "path", None)
        methods = set(getattr(route, "methods", None) or [])
        if path == "/api/mini/order" and "POST" in methods:
            continue
        kept.append(route)
    app.router.routes[:] = kept

    @app.post("/api/mini/order")
    async def mini_order(request: Request):
        body = await request.json()
        uid = require_webapp_user(init_data=str(body.get("init_data") or ""), body=body)
        key = str(body.get("plan") or "year")
        rail = str(body.get("rail") or "stars")
        if not uid:
            raise HTTPException(400, detail="bad user")
        blocked = await deny_json(uid)
        if blocked:
            return blocked
        if not PLATFORM_BOT_TOKEN:
            raise HTTPException(503, detail="bot not ready")
        db = get_session()
        try:
            key = ensure_plan_key(db, key)
            meta = plan_info(db, key)
            tenant = get_or_create_tenant(db, uid)
            coupon_obj = None
            coupon_code = str(body.get("coupon") or "").strip()
            if coupon_code:
                coupon_obj = find_coupon(db, coupon_code)
                err = coupon_error(db, coupon_obj, tenant_id=tenant.id)
                if err:
                    return JSONResponse({"error": err}, status_code=400)
                kind = (coupon_obj.kind or "days").strip().lower()
                if kind not in {"percent", "discount"}:
                    return JSONResponse(
                        {"error": "赠送天数码请到「我的」页兑换，开通页只用折扣码"},
                        status_code=400,
                    )
            info = user_from_init(str(body.get("init_data") or ""))
            save_paid_profile(
                db,
                tenant,
                SimpleNamespace(
                    id=uid,
                    username=body.get("username") or info.get("username") or None,
                    full_name=body.get("display_name") or info.get("full_name") or "",
                ),
            )
            _drop_open_orders(db, tenant.id)
            label = re.sub(r"[^A-Za-z0-9 ]+", "", str(meta.get("label") or key))[:24] or "Pass"
            if rail == "usdt":
                addr = get_setting(db, "usdt_address", USDT_ADDRESS)
                if not addr:
                    return JSONResponse({"error": "尚未配置 USDT 地址"}, status_code=400)
                code = new_code()
                usdt_price = plan_usdt(db, key)
                if coupon_obj:
                    usdt_price = apply_percent(usdt_price, coupon_obj.value_days, stars=False)
                amount = unique_usdt_amount(db, usdt_price)
                db.add(
                    Order(
                        public_code=code,
                        tenant_id=tenant.id,
                        rail="usdt",
                        plan=key,
                        period_days=meta["days"],
                        amount=amount,
                        currency="USDT",
                        chain=USDT_CHAIN,
                        pay_address=addr,
                        status="pending",
                        expires_at=utcnow() + timedelta(minutes=20),
                    )
                )
                if coupon_obj:
                    mark_redeemed(db, coupon_obj, tenant_id=tenant.id, tg_id=uid, days=0)
                db.commit()
                return {
                    "ok": True,
                    "code": code,
                    "amount": f"{amount:g}",
                    "address": addr,
                    "chain": USDT_CHAIN,
                    "discount": int(coupon_obj.value_days) if coupon_obj else 0,
                }
            price = int(plan_stars(db, key))
            if coupon_obj:
                price = int(apply_percent(price, coupon_obj.value_days, stars=True))
            payload = _safe_payload(key, tenant.id)
            db.add(
                Order(
                    public_code=new_code(),
                    tenant_id=tenant.id,
                    rail="stars",
                    plan=key,
                    period_days=meta["days"],
                    amount=price,
                    currency="XTR",
                    status="pending",
                    payload=payload,
                    expires_at=utcnow() + timedelta(hours=24),
                )
            )
            db.commit()
            inv_body = {
                "title": "HeYanHQ Pass",
                "description": "Official membership",
                "payload": payload,
                "currency": "XTR",
                "prices": [{"label": "Pass", "amount": int(price)}],
            }
            sent = await _tg_json("sendInvoice", {"chat_id": int(uid), **inv_body})
            if sent.get("ok"):
                if coupon_obj:
                    mark_redeemed(db, coupon_obj, tenant_id=tenant.id, tg_id=uid, days=0)
                    db.commit()
                return {
                    "ok": True,
                    "sent": True,
                    "payload": payload,
                    "amount": int(price),
                    "discount": int(coupon_obj.value_days) if coupon_obj else 0,
                }
            link = await _tg_json("createInvoiceLink", inv_body)
            if not link.get("ok"):
                err = sent.get("description") or link.get("description") or "无法创建 Stars 账单"
                return JSONResponse({"error": f"Stars账单失败：{err}"}, status_code=400)
            raw = str(link.get("result") or "")
            match = _SLUG_RE.search(raw)
            invoice = ("https://t.me/$" + match.group(1)) if match else raw
            if coupon_obj:
                mark_redeemed(db, coupon_obj, tenant_id=tenant.id, tg_id=uid, days=0)
                db.commit()
            return {
                "ok": True,
                "sent": False,
                "invoice": invoice,
                "payload": payload,
                "amount": int(price),
                "discount": int(coupon_obj.value_days) if coupon_obj else 0,
            }
        finally:
            db.close()
