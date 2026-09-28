from __future__ import annotations

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


def _drop_open_orders(db, tenant_id: int) -> None:
    from app.services import add_event, open_order

    while True:
        order = open_order(db, tenant_id)
        if not order:
            return
        add_event(db, order, "canceled", "replaced_by_new_checkout")
        db.commit()


def remount_mini_order(app) -> None:
    """Replace /api/mini/order so percent coupons change the billed amount."""
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
                if (coupon_obj.kind or "days").strip().lower() != "percent":
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
            price = plan_stars(db, key)
            if coupon_obj:
                price = int(apply_percent(price, coupon_obj.value_days, stars=True))
            payload = f"stars:{key}:{tenant.id}:{new_code()}"
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
            if coupon_obj:
                mark_redeemed(db, coupon_obj, tenant_id=tenant.id, tg_id=uid, days=0)
            db.commit()
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.post(
                    f"https://api.telegram.org/bot{PLATFORM_BOT_TOKEN}/createInvoiceLink",
                    json={
                        "title": f"平台登记·{meta['label']}",
                        "description": "开通后可保存平台登记资料",
                        "payload": payload,
                        "provider_token": "",
                        "currency": "XTR",
                        "prices": [{"label": meta["label"], "amount": int(price)}],
                    },
                )
                data = r.json()
            if not data.get("ok"):
                return JSONResponse({"error": data.get("description", "无法创建 Stars 账单")}, status_code=400)
            return {
                "ok": True,
                "invoice": data["result"],
                "payload": payload,
                "amount": int(price),
                "discount": int(coupon_obj.value_days) if coupon_obj else 0,
            }
        finally:
            db.close()
