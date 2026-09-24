from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.config import ADMIN_TG_IDS
from app.db import Base, get_session
from app.models import utcnow
from app.plans import list_plans
from app.services import add_admin_audit, get_or_create_tenant
from app.tg_webapp import require_webapp_user


class Coupon(Base):
    __tablename__ = "coupons"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(16), default="days")  # days | discount_days
    value_days: Mapped[int] = mapped_column(Integer, default=0)
    max_redemptions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    redeemed_count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CouponRedemption(Base):
    __tablename__ = "coupon_redemptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    coupon_id: Mapped[int] = mapped_column(ForeignKey("coupons.id"), index=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    tg_id: Mapped[int] = mapped_column(Integer, index=True)
    days_granted: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


def _uid(body=None, user_id: int = 0, init_data: str = "") -> int:
    del user_id
    return require_webapp_user(init_data=init_data, body=body)


def _admin(body=None, user_id: int = 0, init_data: str = "") -> int:
    uid = _uid(body, user_id, init_data)
    if uid not in ADMIN_TG_IDS:
        return 0
    return uid


def redeem_coupon(db: Session, *, tenant_id: int, tg_id: int, code: str) -> tuple[bool, str, int]:
    raw = (code or "").strip().upper()
    if not raw:
        return False, "缺少兑换码", 0
    coupon = db.scalar(select(Coupon).where(Coupon.code == raw))
    if not coupon:
        return False, "兑换码无效", 0
    if coupon.expires_at and coupon.expires_at < utcnow():
        return False, "兑换码已过期", 0
    if coupon.max_redemptions is not None and coupon.redeemed_count >= coupon.max_redemptions:
        return False, "兑换码已兑完", 0
    prior = db.scalar(
        select(CouponRedemption).where(
            CouponRedemption.coupon_id == coupon.id,
            CouponRedemption.tenant_id == tenant_id,
        )
    )
    if prior:
        return False, "已兑换过该码", 0
    days = max(0, int(coupon.value_days or 0))
    if days <= 0:
        return False, "兑换码未配置天数", 0
    from app.models import Tenant

    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        return False, "用户不存在", 0
    base = utcnow()
    if tenant.paid_until and tenant.paid_until > base:
        base = tenant.paid_until
    tenant.paid_until = base + timedelta(days=days)
    if tenant.status not in {"owner", "suspended"}:
        tenant.status = "active"
    coupon.redeemed_count = int(coupon.redeemed_count or 0) + 1
    db.add(
        CouponRedemption(
            coupon_id=coupon.id,
            tenant_id=tenant_id,
            tg_id=int(tg_id),
            days_granted=days,
        )
    )
    return True, f"已兑换 {days} 天", days


def mount_wave3(app) -> None:
    @app.get("/api/mini/plans")
    async def public_plans():
        db = get_session()
        try:
            return {"ok": True, "plans": list_plans(db)}
        finally:
            db.close()

    @app.get("/api/mini/admin/coupons")
    async def admin_list_coupons(user_id: int = 0, init_data: str = ""):
        if not _admin(user_id=user_id, init_data=init_data):
            return JSONResponse({"error": "仅管理员"}, status_code=403)
        db = get_session()
        try:
            rows = list(db.scalars(select(Coupon).order_by(Coupon.id.desc()).limit(100)))
            return {
                "ok": True,
                "coupons": [
                    {
                        "id": c.id,
                        "code": c.code,
                        "kind": c.kind,
                        "value_days": c.value_days,
                        "max_redemptions": c.max_redemptions,
                        "redeemed_count": c.redeemed_count,
                        "expires_at": c.expires_at.isoformat() if c.expires_at else "",
                        "note": c.note or "",
                    }
                    for c in rows
                ],
            }
        finally:
            db.close()

    @app.post("/api/mini/admin/coupons")
    async def admin_save_coupon(request: Request):
        body = await request.json()
        admin = _admin(body=body)
        if not admin:
            return JSONResponse({"error": "仅管理员"}, status_code=403)
        code = str(body.get("code") or "").strip().upper() or ("CP-" + secrets.token_hex(3).upper())
        try:
            days = max(1, int(body.get("value_days") or body.get("days") or 7))
        except (TypeError, ValueError):
            days = 7
        max_r = body.get("max_redemptions")
        try:
            max_r = int(max_r) if max_r not in (None, "") else None
        except (TypeError, ValueError):
            max_r = None
        db = get_session()
        try:
            row = db.scalar(select(Coupon).where(Coupon.code == code))
            if not row:
                row = Coupon(code=code)
                db.add(row)
            row.kind = str(body.get("kind") or "days")[:16]
            row.value_days = days
            row.max_redemptions = max_r
            row.note = str(body.get("note") or "")[:200] or None
            exp = body.get("expires_at")
            if exp:
                try:
                    row.expires_at = datetime.fromisoformat(str(exp).replace("Z", ""))
                except ValueError:
                    pass
            add_admin_audit(db, admin, "coupon_save", target_type="coupon", target_id=code, detail=f"days={days}")
            db.commit()
            return {"ok": True, "code": row.code, "value_days": row.value_days}
        finally:
            db.close()

    @app.post("/api/mini/coupon/redeem")
    async def redeem(request: Request):
        body = await request.json()
        uid = _uid(body=body)
        if not uid:
            return JSONResponse({"error": "未登录"}, status_code=401)
        db = get_session()
        try:
            tenant = get_or_create_tenant(db, uid)
            ok, msg, days = redeem_coupon(db, tenant_id=tenant.id, tg_id=uid, code=str(body.get("code") or ""))
            if not ok:
                return JSONResponse({"error": msg}, status_code=400)
            db.commit()
            return {"ok": True, "message": msg, "days": days, "paid_until": str(tenant.paid_until or "")}
        finally:
            db.close()
