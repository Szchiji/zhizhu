from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import ADMIN_TG_IDS, PLAN_DEFAULT, STARS_MONTHLY, USDT_YEARLY
from app.models import Identity, Order, OrderEvent, Setting, Tenant, utcnow

USER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,31}$")
SKIP_NAMES = {
    "https",
    "http",
    "www",
    "telegram",
    "zhizhusp_bot",
    "start",
    "join",
}
JST = ZoneInfo("Asia/Tokyo")


def is_staff(tg_id: int | None) -> bool:
    return bool(tg_id) and bool(ADMIN_TG_IDS) and int(tg_id) in ADMIN_TG_IDS


def mark_staff_tenant(db: Session, tenant: Tenant) -> Tenant:
    if not is_staff(tenant.owner_tg_id) or tenant.status == "suspended":
        return tenant
    if tenant.status != "owner" or tenant.plan != "owner":
        tenant.status = "owner"
        tenant.plan = "owner"
        db.commit()
    return tenant


def get_or_create_tenant(db: Session, owner_tg_id: int) -> Tenant:
    tenant = db.scalar(select(Tenant).where(Tenant.owner_tg_id == owner_tg_id))
    if tenant:
        return mark_staff_tenant(db, tenant)
    if is_staff(owner_tg_id):
        tenant = Tenant(owner_tg_id=owner_tg_id, status="owner", plan="owner")
    else:
        tenant = Tenant(owner_tg_id=owner_tg_id, status="unpaid", plan=PLAN_DEFAULT)
    db.add(tenant)
    db.flush()
    db.add(Identity(tenant_id=tenant.id, alert_text="此为官方登记账号"))
    db.commit()
    db.refresh(tenant)
    return tenant


def tenant_usable(tenant: Tenant, at: datetime | None = None) -> bool:
    at = at or utcnow()
    if tenant.status == "suspended":
        return False
    if tenant.status == "owner" or is_staff(tenant.owner_tg_id):
        return True
    return bool(tenant.paid_until and tenant.paid_until > at)


def parse_username(text: str) -> str:
    raw = (text or "").strip()
    if re.search(r"https?://|t\.me/", raw, re.I):
        m = re.search(r"@([A-Za-z][A-Za-z0-9_]{3,31})", raw)
        name = m.group(1) if m else ""
        return "" if name.lower() in SKIP_NAMES else name
    for prefix in ("核验", "查询", "verify", "q_"):
        if raw.lower().startswith(prefix):
            raw = raw[len(prefix) :].strip()
    raw = raw.lstrip("@")
    token = re.split(r"[\s/?=&]+", raw)[0] if raw else ""
    token = token.strip("@")
    if not USER_RE.fullmatch(token) or token.lower() in SKIP_NAMES:
        return ""
    return token


def fmt_until(dt) -> str:
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(JST).strftime("%Y-%m-%d %H:%M")


def find_paid_by_tg_id(db: Session, tg_id: int) -> Identity | None:
    if not tg_id:
        return None
    ident = db.scalar(select(Identity).where(Identity.official_user_id == int(tg_id)))
    tenant = db.get(Tenant, ident.tenant_id) if ident else None
    if not tenant:
        tenant = db.scalar(select(Tenant).where(Tenant.owner_tg_id == int(tg_id)))
        ident = db.scalar(select(Identity).where(Identity.tenant_id == tenant.id)) if tenant else None
    if ident and tenant and tenant_usable(tenant):
        return ident
    return None


def find_paid_identity(db: Session, username: str) -> Identity | None:
    name = parse_username(username)
    if not name:
        return None
    ident = db.scalar(select(Identity).where(Identity.username.ilike(name)))
    if not ident:
        return None
    tenant = db.get(Tenant, ident.tenant_id)
    if tenant and tenant_usable(tenant):
        return ident
    return None


def save_paid_profile(db: Session, tenant: Tenant, user) -> Identity:
    ident = db.scalar(select(Identity).where(Identity.tenant_id == tenant.id))
    if not ident:
        ident = Identity(tenant_id=tenant.id, alert_text="此为官方登记账号")
        db.add(ident)
    if user:
        uname = getattr(user, "username", None)
        if uname:
            ident.username = str(uname).lstrip("@")[:32]
        uid = getattr(user, "id", None)
        if uid:
            try:
                ident.official_user_id = int(uid)
            except (TypeError, ValueError):
                pass
        name = getattr(user, "full_name", None) or ""
        if name and not ident.display_name:
            ident.display_name = str(name).strip()[:64]
    db.commit()
    db.refresh(ident)
    return ident


def open_order(db: Session, tenant_id: int) -> Order | None:
    return db.scalar(
        select(Order)
        .where(Order.tenant_id == tenant_id, Order.status.in_(("draft", "pending", "confirming")))
        .order_by(Order.id.desc())
    )


def new_code() -> str:
    return "VH-" + secrets.token_hex(3).upper()


def get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.get(Setting, key)
    return row.value if row and row.value != "" else default


def set_setting(db: Session, key: str, value: str) -> None:
    row = db.get(Setting, key)
    if row:
        row.value = value
        row.updated_at = utcnow()
    else:
        db.add(Setting(key=key, value=value, updated_at=utcnow()))
    db.commit()


def stars_price(db: Session) -> int:
    raw = get_setting(db, "stars_monthly", str(STARS_MONTHLY))
    try:
        n = int(float(raw))
    except ValueError:
        n = STARS_MONTHLY
    return max(1, n)


def usdt_price(db: Session) -> float:
    raw = get_setting(db, "usdt_yearly", str(USDT_YEARLY))
    try:
        n = float(raw)
    except ValueError:
        n = USDT_YEARLY
    return max(0.01, n)


def add_event(db: Session, order: Order, dest: str, reason: str) -> None:
    db.add(
        OrderEvent(
            order_id=order.id,
            from_status=order.status,
            to_status=dest,
            reason=reason,
        )
    )
    order.status = dest


def activate_order(db: Session, order: Order) -> Tenant:
    tenant = db.get(Tenant, order.tenant_id)
    base = utcnow()
    if tenant.paid_until and tenant.paid_until > base:
        base = tenant.paid_until
    period_end = base + timedelta(days=order.period_days)
    tenant.paid_until = period_end
    if tenant.status != "owner":
        tenant.status = "active"
    tenant.plan = order.plan
    order.paid_at = utcnow()
    order.period_start = base
    order.period_end = period_end
    add_event(db, order, "active", "entitlement_granted")
    db.commit()
    return tenant
