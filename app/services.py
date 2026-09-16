from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import PLAN_DEFAULT, TRIAL_DAYS
from app.models import Identity, Order, OrderEvent, Tenant, utcnow


def get_or_create_tenant(db: Session, owner_tg_id: int) -> Tenant:
    tenant = db.scalar(select(Tenant).where(Tenant.owner_tg_id == owner_tg_id))
    if tenant:
        return tenant
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
    tenant.status = "active"
    tenant.plan = order.plan
    order.paid_at = utcnow()
    order.period_start = base
    order.period_end = period_end
    add_event(db, order, "active", "entitlement_granted")
    db.commit()
    return tenant
