from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from app.models import Order, OrderEvent, Tenant, utcnow


def revoke_order(db: Session, order: Order, *, reason: str = "admin_revoke") -> Tenant:
    """Mark order refunded/revoked and pull back entitlement days when possible.

    Internal bookkeeping only. Stars official refund is handled by
    app.stars_refund.refund_stars_for_order (called from admin revoke).
    """
    tenant = db.get(Tenant, order.tenant_id)
    if order.status in {"refunded", "revoked"}:
        return tenant
    days = int(order.period_days or 0)
    if tenant and days > 0 and tenant.paid_until and tenant.status != "owner":
        new_until = tenant.paid_until - timedelta(days=days)
        now = utcnow()
        if new_until <= now:
            tenant.paid_until = None
            if tenant.status == "active":
                tenant.status = "unpaid"
        else:
            tenant.paid_until = new_until
    db.add(
        OrderEvent(
            order_id=order.id,
            from_status=order.status,
            to_status="refunded",
            reason=(reason or "")[:64],
        )
    )
    order.status = "refunded"
    return tenant
