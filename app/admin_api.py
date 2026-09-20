from __future__ import annotations

from datetime import timedelta

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import or_, select

from app.access import normalize_channel
from app.bot_avatar import router as avatar_router
from app.card_admin import mount_card_admin
from app.config import ADMIN_TG_IDS, USDT_ADDRESS
from app.db import get_session
from app.home import load_home, save_home
from app.models import Identity, Order, Tenant, utcnow
from app.plans import clone_on, plan_stars, plan_usdt, price_board, set_clone
from app.services import activate_order, add_event, fmt_until, get_or_create_tenant, get_setting, open_order, parse_username, set_setting
from app.tg_webapp import require_webapp_user


def _uid(body: dict | None = None, user_id: int = 0, init_data: str = "") -> int:
    """Identity from verified Telegram WebApp init_data only (ignores bare user_id)."""
    del user_id  # never trust client-supplied user_id as proof of identity
    return require_webapp_user(init_data=init_data, body=body)


def _admin_id(body: dict | None = None, user_id: int = 0, init_data: str = "") -> int:
    uid = _uid(body, user_id, init_data)
    if uid not in ADMIN_TG_IDS:
        return 0
    return uid


def _dump_user(tenant: Tenant) -> dict:
    ident = tenant.identity
    return {
        "tenant_id": tenant.id,
        "tg_id": tenant.owner_tg_id,
        "status": tenant.status,
        "plan": tenant.plan,
        "paid_until": fmt_until(tenant.paid_until) if tenant.paid_until else "",
        "username": ident.username if ident else "",
        "display_name": ident.display_name if ident else "",
        "official_user_id": ident.official_user_id if ident else None,
    }


def _days(body) -> int:
    try:
        days = int(float(body.get("days") or 365))
    except (TypeError, ValueError):
        days = 365
    return max(1, min(days, 3650))


def mount_admin(app) -> None:
    app.include_router(avatar_router)
    mount_card_admin(app)

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
                pending.append({"code": o.public_code, "amount": f"{float(o.amount):g}", "status": o.status, "txid": o.txid or ""})
            orders = []
            for o in db.scalars(select(Order).order_by(Order.id.desc()).limit(20)):
                tenant = db.get(Tenant, o.tenant_id)
                orders.append({
                    "code": o.public_code,
                    "rail": o.rail,
                    "amount": f"{float(o.amount):g}",
                    "status": o.status,
                    "tg_id": tenant.owner_tg_id if tenant else None,
                    "txid": o.txid or "",
                })
            return {
                "ok": True,
                "board": price_board(db),
                "stars": plan_stars(db, "year"),
                "usdt": f"{plan_usdt(db, 'year'):g}",
                "address": get_setting(db, "usdt_address", USDT_ADDRESS),
                "clone": clone_on(db),
                "pending": pending,
                "orders": orders,
                "remind_enabled": get_setting(db, "remind_enabled", "1"),
                "remind_days": get_setting(db, "remind_days", "7"),
                "remind_text": get_setting(db, "remind_text", ""),
                "force_channel": get_setting(db, "force_channel", ""),
                "force_channel_on": get_setting(db, "force_channel_on", "0"),
                "home": load_home(db),
            }
        finally:
            db.close()

    @app.get("/api/mini/admin/users")
    async def admin_users(q: str = "", user_id: int = 0, init_data: str = ""):
        if not _admin_id(user_id=user_id, init_data=init_data):
            return JSONResponse({"error": "仅管理员"}, status_code=403)
        raw = (q or "").strip()
        if not raw:
            return {"ok": True, "users": []}
        db = get_session()
        try:
            rows: list[Tenant] = []
            if raw.isdigit():
                tg = int(raw)
                rows = list(db.scalars(select(Tenant).where(or_(Tenant.owner_tg_id == tg, Tenant.id == tg))))
                ident = db.scalar(select(Identity).where(Identity.official_user_id == tg))
                if ident:
                    t = db.get(Tenant, ident.tenant_id)
                    if t and t not in rows:
                        rows.append(t)
            name = parse_username(raw) or raw.lstrip("@")
            if name:
                idents = list(
                    db.scalars(
                        select(Identity).where(or_(Identity.username.ilike(name), Identity.display_name.ilike(f"%{name}%"))).limit(20)
                    )
                )
                for ident in idents:
                    t = db.get(Tenant, ident.tenant_id)
                    if t and t not in rows:
                        rows.append(t)
            return {"ok": True, "users": [_dump_user(t) for t in rows[:20]]}
        finally:
            db.close()

    @app.post("/api/mini/admin")
    async def admin_act(request: Request):
        body = await request.json()
        admin = _admin_id(body)
        if not admin:
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
                set_setting(db, "stars_year" if rail == "stars" else "usdt_year", str(int(value) if rail == "stars" else f"{value:g}"))
                return {"ok": True, "board": price_board(db)}
            if action == "addr":
                addr = str(body.get("address") or "").strip()
                if not addr.startswith("T") or len(addr) < 30:
                    return JSONResponse({"error": "TRC20 地址无效"}, status_code=400)
                set_setting(db, "usdt_address", addr)
                return {"ok": True}
            if action == "remind":
                try:
                    n = max(0, min(int(float(body.get("days") or 7)), 90))
                except (TypeError, ValueError):
                    n = 7
                enabled = "1" if str(body.get("enabled") or "1") in {"1", "true", "on"} else "0"
                set_setting(db, "remind_days", str(n))
                set_setting(db, "remind_enabled", enabled)
                set_setting(db, "remind_text", str(body.get("text") or "")[:300])
                return {"ok": True, "remind_days": n, "remind_enabled": enabled}
            if action == "channel":
                raw = normalize_channel(str(body.get("channel") or ""))
                set_setting(db, "force_channel", raw)
                if "enabled" in body:
                    on = "1" if str(body.get("enabled")) in {"1", "true", "on"} else "0"
                    set_setting(db, "force_channel_on", on)
                return {"ok": True, "force_channel": raw, "force_channel_on": get_setting(db, "force_channel_on", "0")}
            if action == "channel_toggle":
                on = "0" if get_setting(db, "force_channel_on", "0") == "1" else "1"
                set_setting(db, "force_channel_on", on)
                return {"ok": True, "force_channel_on": on, "force_channel": get_setting(db, "force_channel", "")}
            if action == "home":
                return {"ok": True, "home": save_home(db, body)}
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
            if action in {"user_add", "user_extend"}:
                try:
                    tg_id = int(body.get("tg_id") or 0)
                except (TypeError, ValueError):
                    tg_id = 0
                if not tg_id:
                    return JSONResponse({"error": "请填电报 ID"}, status_code=400)
                tenant = get_or_create_tenant(db, tg_id)
                ident = tenant.identity or Identity(tenant_id=tenant.id)
                uname = parse_username(str(body.get("username") or "")) or ident.username
                if uname:
                    ident.username = uname
                if body.get("display_name"):
                    ident.display_name = str(body.get("display_name"))[:64]
                ident.official_user_id = ident.official_user_id or tg_id
                db.add(ident)
                days = _days(body)
                if tenant.status != "owner":
                    tenant.status = "active"
                    tenant.plan = "year" if days >= 360 else "custom"
                    base = utcnow()
                    if tenant.paid_until and tenant.paid_until > base:
                        base = tenant.paid_until
                    tenant.paid_until = base + timedelta(days=days)
                db.commit()
                return {"ok": True, "user": _dump_user(tenant), "days": days}
            if action in {"user_block", "user_unblock", "user_delete"}:
                try:
                    tg_id = int(body.get("tg_id") or 0)
                except (TypeError, ValueError):
                    tg_id = 0
                target = db.scalar(select(Tenant).where(Tenant.owner_tg_id == tg_id)) if tg_id else None
                if not target and body.get("tenant_id"):
                    target = db.get(Tenant, int(body.get("tenant_id")))
                if not target:
                    return JSONResponse({"error": "用户不存在"}, status_code=404)
                if target.owner_tg_id == admin or target.owner_tg_id in ADMIN_TG_IDS:
                    return JSONResponse({"error": "不能操作管理员"}, status_code=400)
                if action == "user_block":
                    target.status = "suspended"
                    db.commit()
                    return {"ok": True, "user": _dump_user(target)}
                if action == "user_unblock":
                    target.status = "active" if target.paid_until else "unpaid"
                    db.commit()
                    return {"ok": True, "user": _dump_user(target)}
                ident = target.identity
                if ident:
                    ident.username = ""
                    ident.display_name = ""
                    ident.card_text = ""
                    ident.alert_text = ""
                    ident.official_user_id = None
                target.status = "unpaid"
                target.paid_until = None
                db.commit()
                return {"ok": True}
            if action == "user_bind":
                try:
                    tg_id = int(body.get("tg_id") or 0)
                except (TypeError, ValueError):
                    tg_id = 0
                name = parse_username(str(body.get("username") or "")) or str(body.get("username") or "").lstrip("@")
                if not name:
                    return JSONResponse({"error": "请填用户名"}, status_code=400)
                tenant = db.scalar(select(Tenant).where(Tenant.owner_tg_id == tg_id)) if tg_id else None
                if not tenant:
                    ident = db.scalar(select(Identity).where(Identity.official_user_id == tg_id)) if tg_id else None
                    tenant = db.get(Tenant, ident.tenant_id) if ident else None
                if not tenant:
                    return JSONResponse({"error": "未找到该电报ID的开通记录，先搜索用户"}, status_code=404)
                ident = tenant.identity or Identity(tenant_id=tenant.id)
                ident.username = name
                ident.official_user_id = ident.official_user_id or tenant.owner_tg_id
                if body.get("display_name"):
                    ident.display_name = str(body.get("display_name"))[:64]
                db.add(ident)
                db.commit()
                return {"ok": True, "user": _dump_user(tenant)}
            return JSONResponse({"error": "unknown action"}, status_code=400)
        finally:
            db.close()
