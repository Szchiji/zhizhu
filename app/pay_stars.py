from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse

from app.access import get_bot
from app.config import PLATFORM_BOT_TOKEN
from app.coupons import apply_percent, find_coupon, mark_redeemed, widen_coupon_tg_id
from app.db import get_session
from app.models import Order, utcnow
from app.pay_redeem import remount_redeem
from app.plans import ensure_plan_key, plan_info, plan_stars
from app.services import get_or_create_tenant, new_code, save_paid_profile
from app.tg_webapp import require_webapp_user, user_from_init


async def _invoice_link(payload: str, price: int) -> str:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            f"https://api.telegram.org/bot{PLATFORM_BOT_TOKEN}/createInvoiceLink",
            json={
                "title": "HeYanHQ",
                "description": "Official pass",
                "payload": payload,
                "currency": "XTR",
                "prices": [{"label": "Pass", "amount": int(price)}],
            },
        )
        data = r.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("description") or "createInvoiceLink failed")
    raw = str(data.get("result") or "")
    if raw.startswith("$"):
        raw = "https://t.me/" + raw
    elif raw.startswith("t.me/"):
        raw = "https://" + raw
    return raw


def remount_stars_pay(app) -> None:
    widen_coupon_tg_id()
    remount_redeem(app)

    @app.post("/api/mini/pay-stars")
    async def pay_stars(request: Request):
        try:
            body = await request.json()
            uid = require_webapp_user(init_data=str(body.get("init_data") or ""), body=body)
            if not uid:
                return JSONResponse({"error": "未登录"}, status_code=401)
            if not PLATFORM_BOT_TOKEN:
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
                db.commit()
                if coupon_obj:
                    try:
                        mark_redeemed(db, coupon_obj, tenant_id=tenant.id, tg_id=uid, days=0)
                        db.commit()
                    except Exception:
                        db.rollback()
            finally:
                db.close()
            link = await _invoice_link(payload, price)
            return {
                "ok": True,
                "invoice": link,
                "payload": payload,
                "amount": int(price),
                "discount": percent_off,
            }
        except Exception as exc:  # noqa: BLE001
            return JSONResponse({"error": f"Stars下单失败: {exc}"}, status_code=400)
