"""Multi-admin roles (settings-backed) + wave4 rate limits / role APIs."""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.config import ADMIN_TG_IDS
from app.db import get_session
from app.rate_limit import SlidingWindowLimiter
from app.services import get_setting
from app.tg_webapp import require_webapp_user

ROLES = ("owner", "ops", "support")

CAPS: dict[str, set[str]] = {
    "owner": {"*"},
    "ops": {
        "view",
        "confirm",
        "price",
        "users",
        "export",
        "channel",
        "remind",
        "home",
        "card",
        "clone",
        "coupon",
        "revoke",
        "reconcile",
    },
    "support": {"view", "confirm"},
}

ACTION_CAP: dict[str, str] = {
    "price": "price",
    "plans": "price",
    "addr": "price",
    "remind": "remind",
    "channel": "channel",
    "channel_toggle": "channel",
    "home": "home",
    "clone": "clone",
    "confirm": "confirm",
    "user_add": "users",
    "user_extend": "users",
    "user_bind": "users",
    "user_block": "users",
    "user_unblock": "users",
    "user_delete": "users",
}

PATH_CAP: dict[str, str] = {
    "/api/mini/admin/revoke": "revoke",
    "/api/mini/admin/reconcile": "reconcile",
    "/api/mini/admin/coupons": "coupon",
    "/api/mini/admin/export": "export",
    "/api/mini/admin/settings/export": "export",
    "/api/mini/admin/audits": "view",
    "/api/mini/admin/roles": "view",
    "/api/mini/admin/clones": "clone",
    "/api/mini/admin/fx_rate": "price",
}

_admin_rl = SlidingWindowLimiter()
_public_rl = SlidingWindowLimiter()


def load_role_map(db: Session) -> dict[str, str]:
    raw = get_setting(db, "admin_roles", "") or ""
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    out: dict[str, str] = {}
    if not isinstance(data, dict):
        return out
    for k, v in data.items():
        try:
            tid = str(int(str(k).strip()))
        except (TypeError, ValueError):
            continue
        role = str(v or "").strip().lower()
        if role in ROLES:
            out[tid] = role
    return out


def role_of(db: Session, tg_id: int) -> str | None:
    if not tg_id:
        return None
    tid = str(int(tg_id))
    roles = load_role_map(db)
    if tid in roles:
        return roles[tid]
    if int(tg_id) in ADMIN_TG_IDS:
        return "owner"
    return None


def is_admin_tg(db: Session | None, tg_id: int) -> bool:
    if not tg_id:
        return False
    if int(tg_id) in ADMIN_TG_IDS:
        return True
    if db is None:
        return False
    return role_of(db, tg_id) is not None


def has_cap(role: str | None, cap: str) -> bool:
    if not role or role not in CAPS:
        return False
    caps = CAPS[role]
    return "*" in caps or cap in caps


def assert_action_cap(db: Session, tg_id: int, action: str) -> str | None:
    role = role_of(db, tg_id)
    if not role:
        return "仅管理员"
    cap = ACTION_CAP.get(action, "view")
    if not has_cap(role, cap):
        return f"角色 {role} 无权执行 {action}"
    return None


def assert_cap(db: Session, tg_id: int, cap: str) -> str | None:
    role = role_of(db, tg_id)
    if not role:
        return "仅管理员"
    if not has_cap(role, cap):
        return f"角色 {role} 无权：{cap}"
    return None


def _uid(body=None, user_id: int = 0, init_data: str = "") -> int:
    del user_id
    return require_webapp_user(init_data=init_data, body=body)
