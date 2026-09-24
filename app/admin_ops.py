from __future__ import annotations

import csv
import io

from fastapi.responses import JSONResponse, Response
from sqlalchemy import or_, select

from app.config import ADMIN_TG_IDS
from app.db import get_session
from app.models import AdminAudit, Order, Tenant
from app.services import fmt_until
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
