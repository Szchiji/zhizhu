from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import ADMIN_TG_IDS, PLAN_DEFAULT, STARS_MONTHLY, TRIAL_DAYS, USDT_YEARLY
from app.models import Identity, Order, OrderEvent, Setting, Tenant, utcnow


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
        tenant = Tenant(
            owner_tg_id=owner_tg_id,
            status="trial",
            plan=PLAN_DEFAULT,
            trial_ends_at=utcnow() + timedelta(days=TRIAL_DAYS),
        )
    db.add(tenant)
    db.flush()
    db.add(Identity(tenant_id=tenant.id, alert_text="这是公示的官方账号，只认这一个号"))
    db.commit()
    db.refresh(tenant)
    return tenant


def tenant_usable(tenant: Tenant, at: datetime | None = None) -> bool:
    at = at or utcnow()
    if tenant.status == "suspended":
        return False
    if tenant.status == "owner" or is_staff(tenant.owner_tg_id):
        return True
    if tenant.trial_ends_at and at < tenant.trial_ends_at:
        return True
    if tenant.paid_until and at < tenant.paid_until:
        return True
    return False


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


def watch_key(viewer_tg_id: int) -> str:
    return f"watch:{viewer_tg_id}"


def set_watch(db: Session, viewer_tg_id: int, tenant_id: int) -> None:
    set_setting(db, watch_key(viewer_tg_id), str(tenant_id))


def get_watch_tenant(db: Session, viewer_tg_id: int) -> Tenant | None:
    raw = get_setting(db, watch_key(viewer_tg_id), "")
    if not raw.isdigit():
        return None
    return db.get(Tenant, int(raw))


def find_tenant_by_username(db: Session, username: str) -> Tenant | None:
    name = username.lstrip("@").strip()
    if not name:
        return None
    ident = db.scalar(select(Identity).where(Identity.username.ilike(name)))
    if ident:
        return db.get(Tenant, ident.tenant_id)
    return db.scalar(select(Tenant).where(Tenant.bot_username.ilike(name)))


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
    for ts in (tenant.paid_until, tenant.trial_ends_at):
        if ts and ts > base:
            base = ts
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
