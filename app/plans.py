from __future__ import annotations

from app.config import STARS_MONTHLY, USDT_YEARLY
from app.models import Tenant, utcnow
from app.services import get_setting, is_staff, set_setting

PLANS = {
    "half": {"days": 15, "label": "半月"},
    "quarter": {"days": 90, "label": "季度"},
    "year": {"days": 365, "label": "一年"},
    "life": {"days": 36500, "label": "永久"},
}

DEFAULT_STARS = {
    "half": max(1, STARS_MONTHLY // 2 or 200),
    "quarter": max(1, STARS_MONTHLY * 2),
    "year": max(1, STARS_MONTHLY * 8),
    "life": max(1, STARS_MONTHLY * 20),
}
DEFAULT_USDT = {
    "half": max(0.01, round(USDT_YEARLY / 6, 2)),
    "quarter": max(0.01, round(USDT_YEARLY / 3, 2)),
    "year": USDT_YEARLY,
    "life": max(0.01, round(USDT_YEARLY * 3, 2)),
}


def plan_stars(db, key: str) -> int:
    raw = get_setting(db, f"stars_{key}", str(DEFAULT_STARS[key]))
    try:
        return max(1, int(float(raw)))
    except ValueError:
        return DEFAULT_STARS[key]


def plan_usdt(db, key: str) -> float:
    raw = get_setting(db, f"usdt_{key}", str(DEFAULT_USDT[key]))
    try:
        return max(0.01, float(raw))
    except ValueError:
        return DEFAULT_USDT[key]


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
        lines.append(
            f"{meta['label']}：{plan_stars(db, key)}⭐ 或 {plan_usdt(db, key):g} USDT"
        )
    lines.append(f"克隆功能：{'已开启' if clone_on(db) else '已关闭'}")
    return "\n".join(lines)
