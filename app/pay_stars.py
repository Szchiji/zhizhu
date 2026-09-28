from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

from fastapi import Request
from fastapi.responses import JSONResponse
from telegram import LabeledPrice

from app.access import get_bot
from app.coupons import apply_percent, find_coupon, mark_redeemed
from app.db import get_session
from app.models import Order, utcnow
from app.pay_redeem import remount_redeem
from app.plans import ensure_plan_key, plan_info, plan_stars
from app.services import get_or_create_tenant, new_code, save_paid_profile
from app.tg_webapp import require_webapp_user, user_from_init


def remount_stars_pay(app) -> None:
    remount_redeem(app)

    @app.post("/api/mini/pay-stars")
    async def pay_stars(request: Request):
        try:
            body = await request.json()
            uid = require_webapp_user(init_data=str(body.get("init_data") or ""), body=body)
            if not uid:
                return JSONResponse({"error": "未登录"}, status_code=401)
            bot = get_bot()
            if bot is None:
                return JSONResponse({"error": "机器人未就绪"}, status_code=503)
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
                        return JSONResponse({"error": "赠送天数码请到「我的」页兑换"}, status_code=400)
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
                    add_event(db, order, "canceled", "replaced_by_stars_checkout")
                    db.commit()
                price = int(plan_stars(db, key))
                if percent_off:
                    price = int(apply_percent(price, percent_off, stars=True))
                payload = ("s" + key + str(tenant.id) + new_code().replace("-", ""))[:128]
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
                    try:
                        mark_redeemed(db, coupon_obj, tenant_id=tenant.id, tg_id=uid, days=0)
                    except Exception:
                        pass
                db.commit()
            finally:
                db.close()
            await bot.send_invoice(
                chat_id=int(uid),
                title="HeYanHQ",
                description="Official pass",
                payload=payload,
                currency="XTR",
                prices=[LabeledPrice(label="Pass", amount=int(price))],
            )
            return {"ok": True, "sent": True, "payload": payload, "amount": int(price), "discount": percent_off}
        except Exception as exc:  # noqa: BLE001
            return JSONResponse({"error": f"Stars下单失败: {exc}"}, status_code=400)
