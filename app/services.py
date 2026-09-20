from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.brand import bot_aliases, bot_username
from app.config import ADMIN_TG_IDS, PLAN_DEFAULT, STARS_MONTHLY, USDT_YEARLY
from app.models import Identity, Order, OrderEvent, Setting, Tenant, utcnow

USER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,31}$")
SKIP_NAMES = {"https", "http", "www", "telegram", "start", "join"}
CST = ZoneInfo("Asia/Shanghai")


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
    db.add(Identity(tenant_id=tenant.id, alert_text="此为官方登记账号", official_user_id=owner_tg_id))
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


def _skip_names() -> set[str]:
    skip = {n.lower() for n in SKIP_NAMES}
    skip |= bot_aliases()
    return skip


def parse_username(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    skip = _skip_names()
    for alias in list(skip):
        if alias in SKIP_NAMES:
            continue
        raw = re.sub(rf"^@?{re.escape(alias)}\b(?:\s*\+\s*|\s+)", "", raw, flags=re.I).strip()
    for name in re.findall(r"@([A-Za-z][A-Za-z0-9_]{3,31})", text or ""):
        if name.lower() not in skip:
            return name
    if re.search(r"https?://|t\.me/", raw, re.I):
        return ""
    for prefix in ("核验", "查询", "verify"):
        if raw.lower().startswith(prefix):
            raw = raw[len(prefix):].strip()
    token = re.split(r"[\s/?=&]+", raw)[0] if raw else ""
    token = token.lstrip("@")
    if not USER_RE.fullmatch(token) or token.lower() in skip:
        return ""
    return token


def fmt_until(dt) -> str:
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(CST).strftime("%Y-%m-%d %H:%M")


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
    raw = (username or "").strip().lstrip("@")
    name = parse_username(username) or (raw if USER_RE.fullmatch(raw) and raw.lower() not in _skip_names() else "")
    if name and name.lower() in bot_aliases():
        return None
    if not name:
        return None
    ident = db.scalar(select(Identity).where(Identity.username.ilike(name)))
    if not ident:
        return None
    tenant = db.get(Tenant, ident.tenant_id)
    if tenant and tenant_usable(tenant):
        return ident
    return None


async def resolve_paid_identity(db: Session, username: str, bot=None):
    ident = find_paid_identity(db, username)
    name = parse_username(username)
    if name and name.lower() in bot_aliases():
        return None
    if ident or not bot or not name:
        return ident
    try:
        chat = await bot.get_chat("@" + name)
    except Exception:
        return None
    ident = find_paid_by_tg_id(db, chat.id)
    if not ident:
        return None
    ident.username = getattr(chat, "username", None) or name
    if not ident.official_user_id:
        ident.official_user_id = chat.id
    if not (ident.display_name or "").strip():
        ident.display_name = getattr(chat, "full_name", None) or getattr(chat, "first_name", "") or ""
    db.commit()
    return ident


def save_paid_profile(db: Session, tenant: Tenant, user=None) -> Identity:
    ident = db.scalar(select(Identity).where(Identity.tenant_id == tenant.id))
    if not ident:
        ident = Identity(tenant_id=tenant.id, alert_text="此为官方登记账号")
        db.add(ident)
    uid = getattr(user, "id", None) if user is not None else None
    if not uid:
        uid = tenant.owner_tg_id
    try:
        ident.official_user_id = int(uid)
    except (TypeError, ValueError):
        pass
    uname = getattr(user, "username", None) if user is not None else None
    if uname:
        ident.username = str(uname).lstrip("@")[:32]
    name = ""
    if user is not None:
        name = getattr(user, "full_name", None) or getattr(user, "first_name", None) or ""
    if name:
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


def unique_usdt_amount(db: Session, base: float) -> float:
    amount = round(max(0.01, float(base)), 2)
    used = {
        round(float(row.amount), 2)
        for row in db.scalars(
            select(Order).where(Order.rail == "usdt", Order.status.in_(("draft", "pending", "confirming")))
        )
    }
    extra = 0
    while round(amount + extra / 100.0, 2) in used and extra < 99:
        extra += 1
    return round(amount + extra / 100.0, 2)


def add_event(db: Session, order: Order, dest: str, reason: str) -> None:
    db.add(OrderEvent(order_id=order.id, from_status=order.status, to_status=dest, reason=reason))
    order.status = dest


def audit_order_event(db: Session, order: Order, reason: str) -> None:
    """Append an OrderEvent without mutating order.status (denials / idempotent hits)."""
    db.add(
        OrderEvent(
            order_id=order.id,
            from_status=order.status,
            to_status=order.status,
            reason=(reason or "")[:64],
        )
    )


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
    save_paid_profile(db, tenant, SimpleNamespace(id=tenant.owner_tg_id, username=None, full_name=""))
    return tenant


def fulfill_stars_order(db: Session, *, user_id: int = 0, payload: str = "", charge_id: str = "", user=None) -> Tenant | None:
    """Activate a Stars order only when a Telegram payment record exists.

    Real payment path: webhook successful_payment sets telegram_charge_id then activates.
    Client callbacks (/api/mini/stars-paid, /api/mini/me) must not forge activation from a bare pending order.
    """
    order = None
    caller_tenant = None
    if user_id:
        caller_tenant = get_or_create_tenant(db, user_id)
    if payload:
        order = db.scalar(select(Order).where(Order.payload == payload))
        # Do not fulfill another tenant's order via forged payload.
        if order and caller_tenant and order.tenant_id != caller_tenant.id:
            return None
    if not order and caller_tenant:
        order = db.scalar(
            select(Order)
            .where(
                Order.tenant_id == caller_tenant.id,
                Order.rail == "stars",
                Order.status.in_(("pending", "paid")),
            )
            .order_by(Order.id.desc())
        )
    if not order:
        return None
    if order.status == "active":
        return db.get(Tenant, order.tenant_id)
    if charge_id:
        order.telegram_charge_id = charge_id
    # Require Telegram payment signal (charge id) before activating.
    if not order.telegram_charge_id:
        return None
    if order.status == "pending":
        add_event(db, order, "paid", "stars_paid")
    tenant = activate_order(db, order)
    if user is not None:
        save_paid_profile(db, tenant, user)
    elif user_id:
        save_paid_profile(db, tenant, SimpleNamespace(id=user_id, username=None, full_name=""))
    return tenant
