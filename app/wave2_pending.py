from __future__ import annotations

from fastapi.responses import JSONResponse

from app.db import get_session
from app.services import fmt_until, get_or_create_tenant, open_order
from app.tg_webapp import require_webapp_user


def pending_payload(db, tenant) -> dict | None:
    open_o = open_order(db, tenant.id)
    if not open_o or open_o.rail != "usdt" or open_o.status not in {"pending", "confirming", "draft"}:
        return None
    return {
        "code": open_o.public_code,
        "amount": f"{float(open_o.amount):g}",
        "address": open_o.pay_address or "",
        "chain": (open_o.chain or "trc20").upper(),
        "status": open_o.status,
        "expires_at": fmt_until(open_o.expires_at) if open_o.expires_at else "",
    }


def mount_wave2_pending(app) -> None:
    @app.get("/api/mini/pending")
    async def mini_pending(user_id: int = 0, init_data: str = ""):
        try:
            uid = require_webapp_user(init_data=init_data, body=None)
        except Exception:
            uid = 0
        if not uid and user_id:
            uid = int(user_id)
        if not uid:
            return JSONResponse({"error": "未登录"}, status_code=401)
        db = get_session()
        try:
            tenant = get_or_create_tenant(db, uid)
            return {"ok": True, "pending": pending_payload(db, tenant)}
        finally:
            db.close()
