from __future__ import annotations

import json
import re
from typing import Any

from app.config import STARS_MONTHLY, USDT_YEARLY
from app.models import Tenant, utcnow
from app.services import get_setting, is_staff, set_setting

# Static fallback when membership_plans setting is empty.
PLANS = {
    "year": {"days": 365, "label": "一年"},
}

DEFAULT_STARS = {"year": max(1, STARS_MONTHLY * 8)}
DEFAULT_USDT = {"year": USDT_YEARLY}

MEMBERSHIP_PLANS_KEY = "membership_plans"
_PLAN_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,15}$")
_MAX_PLANS = 8


def _default_stars_for(key: str) -> int:
    if key in DEFAULT_STARS:
        return DEFAULT_STARS[key]
    if key == "month":
        return max(1, STARS_MONTHLY)
    if key == "quarter":
        return max(1, STARS_MONTHLY * 3)
    return DEFAULT_STARS["year"]


def _default_usdt_for(key: str) -> float:
    if key in DEFAULT_USDT:
        return DEFAULT_USDT[key]
    if key == "month":
        return max(0.01, round(USDT_YEARLY / 8, 2))
    if key == "quarter":
        return max(0.01, round(USDT_YEARLY / 3, 2))
    return DEFAULT_USDT["year"]


def _normalize_plan_row(row: Any) -> dict | None:
    if not isinstance(row, dict):
        return None
    pid = str(row.get("id") or "").strip().lower()
    if not _PLAN_ID_RE.match(pid):
        return None
    label = str(row.get("label") or pid).strip()[:20] or pid
    try:
        days = int(float(row.get("days") or 0))
    except (TypeError, ValueError):
        return None
    if days < 1 or days > 3650:
        return None
    return {"id": pid, "label": label, "days": days}


def normalize_plans(raw: Any) -> list[dict]:
    """Validate a list of {id, label, days}; drop bad rows; dedupe by id."""
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for row in raw[:_MAX_PLANS]:
        item = _normalize_plan_row(row)
        if not item or item["id"] in seen:
            continue
        seen.add(item["id"])
        out.append(item)
    return out


def list_plan_defs(db) -> list[dict]:
    """Return [{id, label, days}, ...] from settings or static PLANS."""
    raw = get_setting(db, MEMBERSHIP_PLANS_KEY, "")
    if raw:
        try:
            cleaned = normalize_plans(json.loads(raw))
            if cleaned:
                return cleaned
        except Exception:
            pass
    return [{"id": k, "label": v["label"], "days": v["days"]} for k, v in PLANS.items()]


def plans_map(db) -> dict[str, dict]:
    """id -> {days, label} (same shape as module PLANS values)."""
    return {p["id"]: {"days": p["days"], "label": p["label"]} for p in list_plan_defs(db)}


def ensure_plan_key(db, key: str) -> str:
    m = plans_map(db)
    key = str(key or "").strip().lower()
    if key in m:
        return key
    if "year" in m:
        return "year"
    return next(iter(m))


def plan_info(db, key: str) -> dict:
    """Return {id, label, days, stars, usdt} for a plan key."""
    key = ensure_plan_key(db, key)
    meta = plans_map(db)[key]
    return {
        "id": key,
        "label": meta["label"],
        "days": meta["days"],
        "stars": plan_stars(db, key),
        "usdt": plan_usdt(db, key),
    }


def list_plans(db) -> list[dict]:
    """Public catalog for mini/admin: each row has id/label/days/stars/usdt."""
    return [plan_info(db, p["id"]) for p in list_plan_defs(db)]


def save_plan_defs(db, raw: Any) -> list[dict]:
    """Persist membership_plans JSON. Returns list_plans(db) after save."""
    cleaned = normalize_plans(raw)
    if not cleaned:
        raise ValueError("至少需要一个有效套餐（id/label/days）")
    set_setting(db, MEMBERSHIP_PLANS_KEY, json.dumps(cleaned, ensure_ascii=False))
    return list_plans(db)


def plan_stars(db, key: str) -> int:
    key = str(key or "").strip().lower()
    m = plans_map(db)
    if key not in m:
        key = "year" if "year" in m else (next(iter(m)) if m else "year")
    raw = get_setting(db, f"stars_{key}", str(_default_stars_for(key)))
    try:
        return max(1, int(float(raw)))
    except ValueError:
        return _default_stars_for(key)


def plan_usdt(db, key: str) -> float:
    key = str(key or "").strip().lower()
    m = plans_map(db)
    if key not in m:
        key = "year" if "year" in m else (next(iter(m)) if m else "year")
    raw = get_setting(db, f"usdt_{key}", str(_default_usdt_for(key)))
    try:
        return max(0.01, float(raw))
    except ValueError:
        return _default_usdt_for(key)


def set_plan_price(db, key: str, rail: str, amount: float) -> str:
    """Write stars_{key} or usdt_{key}; returns setting key."""
    key = ensure_plan_key(db, key)
    if rail == "stars":
        stored = str(max(1, int(amount)))
        setting_key = f"stars_{key}"
    else:
        stored = f"{max(0.01, float(amount)):g}"
        setting_key = f"usdt_{key}"
    set_setting(db, setting_key, stored)
    return setting_key


def plan_label_for(db, key: str) -> str:
    """Label for display; unknown keys (owner/custom) return the raw key."""
    key = str(key or "").strip()
    if not key:
        return "—"
    m = plans_map(db)
    if key in m:
        return m[key]["label"]
    return key


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
    for p in list_plans(db):
        lines.append(f"{p['label']}：{p['stars']}⭐ 或 {p['usdt']:g} USDT（{p['days']}天）")
    lines.append(f"克隆功能：{'已开启' if clone_on(db) else '已关闭'}")
    return "\n".join(lines)
