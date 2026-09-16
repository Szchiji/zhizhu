from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.config import ADMIN_TG_IDS, USDT_ADDRESS
from app.db import get_session
from app.models import Order
from app.plans import clone_on, plan_stars, plan_usdt, price_board, set_clone
from app.services import activate_order, add_event, get_or_create_tenant, get_setting, open_order, set_setting
from app.tg_webapp import user_id_from_init


def _uid(body: dict | None = None, user_id: int = 0, init_data: str = "") -> int:
    uid = 0
    if init_data:
        uid = user_id_from_init(init_data)
    if not uid and body:
        uid = user_id_from_init(str(body.get("init_data") or ""))
        if not uid:
            try:
                uid = int(body.get("user_id") or 0)
            except (TypeError, ValueError):
                uid = 0
    if not uid:
        uid = int(user_id or 0)
    return uid


def _admin_id(body: dict | None = None, user_id: int = 0, init_data: str = "") -> int:
    uid = _uid(body, user_id, init_data)
    if uid not in ADMIN_TG_IDS:
        return 0
    return uid


def mount_admin(app) -> None:
    @app.post("/api/mini/cancel")
    async def mini_cancel(request: Request):
        body = await request.json()
        uid = _uid(body)
        if not uid:
            return JSONResponse({"error": "未登录"}, status_code=401)
        db = get_session()
        try:
            tenant = get_or_create_tenant(db, uid)
            code = str(body.get("code") or "").upper()
            order = None
            if code:
                order = db.scalar(select(Order).where(Order.public_code == code, Order.tenant_id == tenant.id))
            if not order:
                order = open_order(db, tenant.id)
            if not order or order.status not in {"pending", "confirming", "draft"}:
                return JSONResponse({"error": "没有可取消的订单"}, status_code=400)
            add_event(db, order, "canceled", "user_cancel")
            db.commit()
            return {"ok": True, "code": order.public_code}
        finally:
            db.close()

    @app.get("/api/mini/admin")
    async def admin_board(user_id: int = 0, init_data: str = ""):
        if not _admin_id(user_id=user_id, init_data=init_data):
            return JSONResponse({"error": "仅管理员"}, status_code=403)
        db = get_session()
        try:
            pending = []
            for o in db.scalars(
                select(Order).where(Order.rail == "usdt", Order.status.in_(("pending", "confirming"))).limit(30)
            ):
                pending.append(
                    {
                        "code": o.public_code,
                        "amount": f"{float(o.amount):g}",
                        "status": o.status,
                        "txid": o.txid or "",
                    }
                )
            return {
                "ok": True,
                "board": price_board(db),
                "stars": plan_stars(db, "year"),
                "usdt": f"{plan_usdt(db, 'year'):g}",
                "address": get_setting(db, "usdt_address", USDT_ADDRESS),
                "clone": clone_on(db),
                "pending": pending,
            }
        finally:
            db.close()

    @app.post("/api/mini/admin")
    async def admin_act(request: Request):
        body = await request.json()
        if not _admin_id(body):
            return JSONResponse({"error": "仅管理员"}, status_code=403)
        action = str(body.get("action") or "")
        db = get_session()
        try:
            if action == "price":
                rail = str(body.get("rail") or "stars")
                try:
                    value = float(body.get("amount") or 0)
                except (TypeError, ValueError):
                    raise HTTPException(400, "bad amount")
                if rail == "stars":
                    set_setting(db, "stars_year", str(int(value)))
                else:
                    set_setting(db, "usdt_year", f"{value:g}")
                return {"ok": True, "board": price_board(db)}
            if action == "addr":
                addr = str(body.get("address") or "").strip()
                if not addr.startswith("T") or len(addr) < 30:
                    return JSONResponse({"error": "TRC20 地址无效"}, status_code=400)
                set_setting(db, "usdt_address", addr)
                return {"ok": True}
            if action == "clone":
                set_clone(db, not clone_on(db))
                return {"ok": True, "clone": clone_on(db)}
            if action == "confirm":
                code = str(body.get("code") or "").upper()
                order = db.scalar(select(Order).where(Order.public_code == code))
                if not order:
                    return JSONResponse({"error": "订单不存在"}, status_code=404)
                if order.status in {"active", "paid"}:
                    return {"ok": True, "already": True}
                if body.get("txid"):
                    order.txid = str(body.get("txid"))
                add_event(db, order, "paid", "mini_admin")
                tenant = activate_order(db, order)
                return {"ok": True, "paid_until": str(tenant.paid_until)}
            return JSONResponse({"error": "unknown action"}, status_code=400)
        finally:
            db.close()
