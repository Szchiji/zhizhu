"""Multi-admin roles (settings-backed) + wave4 rate limits / role APIs."""
from __future__ import annotations

import json
import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import ADMIN_TG_IDS
from app.db import get_session
from app.rate_limit import SlidingWindowLimiter
from app.services import add_admin_audit, get_setting, set_setting
from app.tg_webapp import require_webapp_user

log = logging.getLogger("zhizhu.admin_roles")

ROLES = ("owner", "ops", "support")

# Capability sets per role. owner has all.
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

# Map admin POST action -> required capability
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
    """Resolve role. ADMIN_TG_IDS default to owner unless settings override."""
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
    """Return error message if denied, else None."""
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


def mount_wave4(app) -> None:
    @app.get("/api/mini/admin/roles")
    async def get_roles(user_id: int = 0, init_data: str = ""):
        uid = _uid(user_id=user_id, init_data=init_data)
        db = get_session()
        try:
            err = assert_cap(db, uid, "view")
            if err:
                return JSONResponse({"error": err}, status_code=403)
            role = role_of(db, uid)
            mapping = load_role_map(db)
            # Include env admins as owner if not listed
            for aid in ADMIN_TG_IDS:
                mapping.setdefault(str(aid), "owner")
            return {
                "ok": True,
                "me_role": role,
                "roles": mapping,
                "env_admins": sorted(ADMIN_TG_IDS),
            }
        finally:
            db.close()

    @app.post("/api/mini/admin/roles")
    async def set_roles(request: Request):
        body = await request.json()
        uid = _uid(body=body)
        db = get_session()
        try:
            role = role_of(db, uid)
            if not has_cap(role, "*"):
                return JSONResponse({"error": "仅 owner 可改角色"}, status_code=403)
            incoming = body.get("roles")
            if not isinstance(incoming, dict):
                return JSONResponse({"error": "roles 须为对象"}, status_code=400)
            cleaned: dict[str, str] = {}
            for k, v in incoming.items():
                try:
                    tid = str(int(str(k).strip()))
                except (TypeError, ValueError):
                    continue
                r = str(v or "").strip().lower()
                if r in ROLES:
                    cleaned[tid] = r
            set_setting(db, "admin_roles", json.dumps(cleaned, ensure_ascii=False), commit=False)
            add_admin_audit(
                db,
                uid,
                "roles",
                target_type="setting",
                target_id="admin_roles",
                detail=f"n={len(cleaned)}",
            )
            db.commit()
            return {"ok": True, "roles": cleaned}
        finally:
            db.close()

    @app.middleware("http")
    async def wave4_rate_limits(request: Request, call_next):
        path = request.url.path or ""
        client = request.client.host if request.client else "unknown"
        # Admin mutators
        if request.method == "POST" and (
            path.startswith("/api/mini/admin")
            or path in {"/api/mini/coupon/redeem", "/api/mini/profile", "/api/mini/order", "/api/mini/stars-paid", "/api/mini/cancel"}
        ):
            if not _admin_rl.allow(f"mut:{client}:{path}", limit=40, window_sec=60):
                return JSONResponse({"error": "请求过快，请稍后再试"}, status_code=429)
        # Public query endpoints
        if request.method == "GET" and path in {
            "/api/mini/lookup",
            "/api/mini/plans",
            "/api/mini/pending",
            "/api/mini/me",
            "/api/mini/orders",
        }:
            if not _public_rl.allow(f"pub:{client}:{path}", limit=90, window_sec=60):
                return JSONResponse({"error": "请求过快，请稍后再试"}, status_code=429)
        return await call_next(request)
