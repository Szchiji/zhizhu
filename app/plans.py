from __future__ import annotations

from app.config import STARS_MONTHLY, USDT_YEARLY
from app.models import Tenant, utcnow
from app.services import get_setting, is_staff, set_setting

PLANS = {
    "year": {"days": 365, "label": "一年"},
}

DEFAULT_STARS = {"year": max(1, STARS_MONTHLY * 8)}
DEFAULT_USDT = {"year": USDT_YEARLY}


def plan_stars(db, key: str) -> int:
    key = key if key in PLANS else "year"
    raw = get_setting(db, f"stars_{key}", str(DEFAULT_STARS.get(key, DEFAULT_STARS["year"])))
    try:
        return max(1, int(float(raw)))
    except ValueError:
        return DEFAULT_STARS["year"]


def plan_usdt(db, key: str) -> float:
    key = key if key in PLANS else "year"
    raw = get_setting(db, f"usdt_{key}", str(DEFAULT_USDT.get(key, DEFAULT_USDT["year"])))
    try:
        return max(0.01, float(raw))
    except ValueError:
        return DEFAULT_USDT["year"]


def clone_on(db) -> bool:
    return get_setting(db, "clone_enabled", "0") == "1"


def set_clone(db, enabled: bool) -> None:
    set_setting(db, "clone_enabled", "1" if enabled else "0")


def is_paid(tenant: Tenant) -> bool:
    if is_staff(tenant.owner_tg_id) or tenant.status == "owner":
        return True
    if tenant.status == "suspended":
        return False
    return bool(tenant.paid_until and tenant.paid_until > utcnow())


def price_board(db) -> str:
    lines = ["套餐价格"]
    for key, meta in PLANS.items():
        lines.append(f"{meta['label']}：{plan_stars(db, key)}⭐ 或 {plan_usdt(db, key):g} USDT")
    lines.append(f"克隆功能：{'已开启' if clone_on(db) else '已关闭'}")
    return "\n".join(lines)
