from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

from fastapi import Request
from fastapi.responses import JSONResponse

from app.config import USDT_ADDRESS, USDT_CHAIN
from app.coupons import apply_percent, find_coupon, mark_redeemed
from app.db import get_session
from app.models import Order, utcnow
from app.plans import ensure_plan_key, plan_info, plan_usdt
from app.services import get_or_create_tenant, get_setting, new_code, save_paid_profile, unique_usdt_amount
from app.tg_webapp import require_webapp_user, user_from_init


def remount_usdt_pay(app) -> None:
    @app.post("/api/mini/pay-usdt")
    async def pay_usdt(request: Request):
        body = await request.json()
        uid = require_webapp_user(init_data=str(body.get("init_data") or ""), body=body)
        if not uid:
            return JSONResponse({"error": "未登录"}, status_code=401)
        db = get_session()
        try:
            key = ensure_plan_key(db, str(body.get("plan") or "year"))
            meta = plan_info(db, key)
            tenant = get_or_create_tenant(db, uid)
            coupon_obj = None
            coupon_code = str(body.get("coupon") or "").strip()
            if coupon_code:
                coupon_obj = find_coupon(db, coupon_code)
                if not coupon_obj:
                    return JSONResponse({"error": "兑换码无效"}, status_code=400)
                kind = (coupon_obj.kind or "days").strip().lower()
                if kind not in {"percent", "discount"}:
                    return JSONResponse({"error": "赠送天数码请到「我的」页兑换"}, status_code=400)
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
            from app.services import add_event, open_order

            while True:
                order = open_order(db, tenant.id)
                if not order:
                    break
                add_event(db, order, "canceled", "replaced_by_usdt_checkout")
                db.commit()
            addr = get_setting(db, "usdt_address", USDT_ADDRESS)
            if not addr:
                return JSONResponse({"error": "尚未配置 USDT 地址"}, status_code=400)
            price = plan_usdt(db, key)
            if coupon_obj:
                price = apply_percent(price, coupon_obj.value_days, stars=False)
            amount = unique_usdt_amount(db, price)
            code = new_code()
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
                try:
                    mark_redeemed(db, coupon_obj, tenant_id=tenant.id, tg_id=uid, days=0)
                except Exception:
                    pass
            db.commit()
            return {
                "ok": True,
                "code": code,
                "amount": f"{amount:g}",
                "address": addr,
                "chain": USDT_CHAIN,
                "discount": int(coupon_obj.value_days) if coupon_obj else 0,
            }
        finally:
            db.close()
