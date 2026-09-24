from __future__ import annotations

import csv
import io

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import or_, select

from app.config import ADMIN_TG_IDS
from app.db import get_session
from app.models import AdminAudit, Order, Tenant
from app.services import add_admin_audit, fmt_until
from app.wave2_revoke import revoke_order
from app.tg_webapp import require_webapp_user


def _uid(body: dict | None = None, user_id: int = 0, init_data: str = "") -> int:
    del user_id
    return require_webapp_user(init_data=init_data, body=body)


def _admin_id(body: dict | None = None, user_id: int = 0, init_data: str = "") -> int:
    uid = _uid(body, user_id, init_data)
    if uid not in ADMIN_TG_IDS:
        return 0
    return uid


def mount_admin_ops(app) -> None:
    @app.get("/api/mini/admin/audits")
    async def admin_audits(limit: int = 50, action: str = "", q: str = "", user_id: int = 0, init_data: str = ""):
        if not _admin_id(user_id=user_id, init_data=init_data):
            return JSONResponse({"error": "仅管理员"}, status_code=403)
        try:
            lim = max(1, min(int(limit or 50), 100))
        except (TypeError, ValueError):
            lim = 50
        db = get_session()
        try:
            stmt = select(AdminAudit).order_by(AdminAudit.id.desc()).limit(lim)
            act = (action or "").strip()
            if act:
                stmt = stmt.where(AdminAudit.action.ilike(act))
            raw_q = (q or "").strip()
            if raw_q:
                like = f"%{raw_q}%"
                clauses = [AdminAudit.detail.ilike(like), AdminAudit.target_id.ilike(like)]
                if raw_q.isdigit():
                    clauses.append(AdminAudit.admin_tg_id == int(raw_q))
                stmt = stmt.where(or_(*clauses))
            rows = []
            for a in db.scalars(stmt):
                rows.append(
                    {
                        "id": a.id,
                        "admin_tg_id": a.admin_tg_id,
                        "action": a.action,
                        "target_type": a.target_type or "",
                        "target_id": a.target_id or "",
                        "detail": a.detail or "",
                        "created_at": fmt_until(a.created_at) if a.created_at else "",
                    }
                )
            return {"ok": True, "audits": rows}
        finally:
            db.close()

    @app.get("/api/mini/admin/export")
    async def admin_export(kind: str = "orders", user_id: int = 0, init_data: str = ""):
        if not _admin_id(user_id=user_id, init_data=init_data):
            return JSONResponse({"error": "仅管理员"}, status_code=403)
        kind = (kind or "orders").strip().lower()
        if kind not in {"orders", "users"}:
            return JSONResponse({"error": "kind 须为 orders 或 users"}, status_code=400)
        db = get_session()
        try:
            buf = io.StringIO()
            w = csv.writer(buf)
            if kind == "orders":
                w.writerow(["code","rail","plan","amount","currency","status","tg_id","txid","paid_at","period_end","created_at"])
                for o in db.scalars(select(Order).order_by(Order.id.desc()).limit(500)):
                    tenant = db.get(Tenant, o.tenant_id)
                    w.writerow([o.public_code or "", o.rail or "", o.plan or "", f"{float(o.amount):g}" if o.amount is not None else "", o.currency or "", o.status or "", tenant.owner_tg_id if tenant else "", o.txid or "", fmt_until(o.paid_at) if o.paid_at else "", fmt_until(o.period_end) if o.period_end else "", fmt_until(o.created_at) if o.created_at else ""])
                fname = "orders.csv"
            else:
                w.writerow(["tg_id","username","display_name","status","plan","paid_until","official_user_id"])
                for t in db.scalars(select(Tenant).order_by(Tenant.id.desc()).limit(500)):
                    ident = t.identity
                    w.writerow([t.owner_tg_id, ident.username if ident else "", ident.display_name if ident else "", t.status or "", t.plan or "", fmt_until(t.paid_until) if t.paid_until else "", ident.official_user_id if ident else ""])
                fname = "users.csv"
            body = "\ufeff" + buf.getvalue()
            headers = {"Content-Disposition": 'attachment; filename="%s"' % fname}
            return Response(content=body.encode("utf-8"), media_type="text/csv; charset=utf-8", headers=headers)
        finally:
            db.close()


    @app.get("/api/mini/admin/reconcile")
    async def admin_reconcile(limit: int = 50, user_id: int = 0, init_data: str = ""):
        """Read-only USDT order reconciliation: pending/expired/unmatched txids."""
        if not _admin_id(user_id=user_id, init_data=init_data):
            return JSONResponse({"error": "仅管理员"}, status_code=403)
        try:
            lim = max(1, min(int(limit or 50), 200))
        except (TypeError, ValueError):
            lim = 50
        db = get_session()
        try:
            from app.models import utcnow
            now = utcnow()
            rows = list(db.scalars(select(Order).where(Order.rail == "usdt").order_by(Order.id.desc()).limit(lim)))
            out = []
            for o in rows:
                tenant = db.get(Tenant, o.tenant_id)
                flag = ""
                if o.status in {"pending", "confirming", "draft"} and o.expires_at and o.expires_at < now:
                    flag = "expired_unpaid"
                elif o.status == "active" and not o.txid and o.rail == "usdt":
                    flag = "active_without_txid"
                elif o.status in {"pending", "confirming"} and o.txid:
                    flag = "txid_but_not_active"
                elif o.status == "expired":
                    flag = "expired"
                out.append(
                    {
                        "code": o.public_code,
                        "status": o.status,
                        "amount": f"{float(o.amount):g}",
                        "txid": o.txid or "",
                        "tg_id": tenant.owner_tg_id if tenant else None,
                        "expires_at": fmt_until(o.expires_at) if o.expires_at else "",
                        "paid_at": fmt_until(o.paid_at) if o.paid_at else "",
                        "flag": flag,
                    }
                )
            return {"ok": True, "orders": out}
        finally:
            db.close()

    @app.post("/api/mini/admin/revoke")
    async def admin_revoke(request: Request):
        """Internal Stars/USDT revoke: mark refunded and pull back paid_until days."""
        body = await request.json()
        admin = _admin_id(body=body)
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
            tenant = revoke_order(db, order, reason="admin_revoke")
            add_admin_audit(
                db,
                admin,
                "revoke",
                target_type="order",
                target_id=order.public_code,
                detail=f"rail={order.rail};tenant={order.tenant_id};paid_until={fmt_until(tenant.paid_until) if tenant and tenant.paid_until else ''}",
            )
            db.commit()
            return {
                "ok": True,
                "code": order.public_code,
                "status": order.status,
                "paid_until": fmt_until(tenant.paid_until) if tenant and tenant.paid_until else "",
            }
        finally:
            db.close()
