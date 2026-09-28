from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

from fastapi import Request
from fastapi.responses import JSONResponse

from app.config import USDT_ADDRESS, USDT_CHAIN
from app.coupons import apply_percent, find_coupon
from app.db import get_session
from app.models import Order, utcnow
from app.plans import ensure_plan_key, plan_info, plan_usdt
from app.services import get_or_create_tenant, get_setting, new_code, save_paid_profile, unique_usdt_amount
from app.tg_webapp import require_webapp_user, user_from_init


def remount_usdt_pay(app) -> None:
    @app.post("/api/mini/pay-usdt")
    async def pay_usdt(request: Request):
        try:
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
                percent_off = 0
                coupon_code = str(body.get("coupon") or "").strip().upper()
                if coupon_code:
                    coupon_obj = find_coupon(db, coupon_code)
                    if not coupon_obj:
                        return JSONResponse({"error": "兑换码无效"}, status_code=400)
                    kind = (coupon_obj.kind or "days").strip().lower()
                    if kind not in {"percent", "discount"}:
                        return JSONResponse(
                            {"error": "这是赠送天数码，请到「我的」页兑换；开通页请用折扣码"},
                            status_code=400,
                        )
                    percent_off = max(1, min(90, int(coupon_obj.value_days or 0)))
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
                price = float(plan_usdt(db, key))
                if percent_off:
                    price = float(apply_percent(price, percent_off, stars=False))
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
                db.commit()
                return {
                    "ok": True,
                    "code": code,
                    "amount": f"{amount:g}",
                    "address": addr,
                    "chain": USDT_CHAIN,
                    "discount": percent_off,
                }
            finally:
                db.close()
        except Exception as exc:  # noqa: BLE001
            return JSONResponse({"error": f"USDT下单失败: {type(exc).__name__}"}, status_code=400)
