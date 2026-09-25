"""Wave9: wrap admin revoke to call Telegram Stars refundStarPayment."""
from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.db import get_session
from app.models import Order, Tenant
from app.services import add_admin_audit, fmt_until
from app.stars_refund import refund_stars_for_order
from app.wave2_revoke import revoke_order

log = logging.getLogger("zhizhu.wave9_revoke")


def _drop_revoke_routes(app) -> int:
    """Remove prior POST /api/mini/admin/revoke so our handler is authoritative."""
    kept = []
    dropped = 0
    for route in list(app.router.routes):
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        if path == "/api/mini/admin/revoke" and "POST" in methods:
            dropped += 1
            continue
        kept.append(route)
    if dropped:
        app.router.routes = kept
    return dropped


def mount_wave9_revoke(app) -> None:
    """Replace /api/mini/admin/revoke with Stars-refund-aware handler."""
    import app.admin_ops as ao

    n = _drop_revoke_routes(app)
    log.info("wave9 dropped %s prior revoke route(s)", n)

    @app.post("/api/mini/admin/revoke")
    async def admin_revoke_stars(request: Request):
        body = await request.json()
        admin = ao._admin_id(body=body)
        if not admin:
            return JSONResponse({"error": "仅管理员"}, status_code=403)
        code = str(body.get("code") or "").upper().strip()
        if not code:
            return JSONResponse({"error": "缺少订单号"}, status_code=400)
        db = get_session()
        try:
            order = db.scalar(select(Order).where(Order.public_code == code))
            if not order:
                return JSONResponse({"error": "订单不存在"}, status_code=404)
            if order.status not in {"active", "paid", "confirming"}:
                return JSONResponse({"error": f"订单状态 {order.status} 不可撤销"}, status_code=400)
            tenant = db.get(Tenant, order.tenant_id)
            stars = await refund_stars_for_order(order, tenant)
            tenant = revoke_order(db, order, reason="admin_revoke")
            sr_bit = (
                f"stars_ok={stars.get('ok')};already={stars.get('already')};"
                f"skipped={stars.get('skipped')};err={stars.get('error') or ''}"
            )
            add_admin_audit(
                db,
                admin,
                "revoke",
                target_type="order",
                target_id=order.public_code,
                detail=(
                    f"rail={order.rail};tenant={order.tenant_id};"
                    f"paid_until={fmt_until(tenant.paid_until) if tenant and tenant.paid_until else ''};"
                    f"{sr_bit}"
                )[:500],
            )
            db.commit()
            msg = "已撤销开通"
            if stars.get("ok") and not stars.get("already"):
                msg = "已撤销开通，并完成 Stars 官方退款"
            elif stars.get("already"):
                msg = "已撤销开通（Stars 侧此前已退款）"
            elif (order.rail or "").lower() == "stars" and stars.get("attempted") and not stars.get("ok"):
                msg = "已内部撤销；Stars 官方退款失败，请人工核对"
            elif (order.rail or "").lower() == "stars" and stars.get("skipped"):
                msg = "已内部撤销（无 charge 或未配置 Bot，未调用官方退款）"
            return {
                "ok": True,
                "code": order.public_code,
                "status": order.status,
                "paid_until": fmt_until(tenant.paid_until) if tenant and tenant.paid_until else "",
                "message": msg,
                "stars_refund": stars,
            }
        finally:
            db.close()

    log.info("wave9 stars revoke mounted")
