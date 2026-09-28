from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from app.coupons import redeem_coupon
from app.db import get_session
from app.services import get_or_create_tenant
from app.tg_webapp import require_webapp_user


def remount_redeem(app) -> None:
    @app.post("/api/mini/coupon/redeem")
    async def redeem(request: Request):
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "请重新点兑换"}, status_code=400)
        uid = require_webapp_user(init_data=str(body.get("init_data") or ""), body=body)
        if not uid:
            return JSONResponse({"error": "未登录"}, status_code=401)
        db = get_session()
        try:
            tenant = get_or_create_tenant(db, uid)
            ok, msg, days = redeem_coupon(
                db, tenant_id=tenant.id, tg_id=uid, code=str(body.get("code") or "")
            )
            if not ok:
                return JSONResponse({"error": msg}, status_code=400)
            db.commit()
            return {
                "ok": True,
                "message": msg,
                "days": days,
                "paid_until": str(tenant.paid_until or ""),
            }
        except Exception as exc:  # noqa: BLE001
            return JSONResponse({"error": f"兑换失败: {type(exc).__name__}"}, status_code=400)
        finally:
            db.close()
