"""Wave4 mount: patch admin identity + rate/cap middleware."""
from __future__ import annotations

import json
import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.requests import Request as StarletteRequest

from app.admin_roles import (
    ACTION_CAP,
    PATH_CAP,
    assert_cap,
    has_cap,
    is_admin_tg,
    load_role_map,
    role_of,
    _uid,
    _admin_rl,
    _public_rl,
    ROLES,
)
from app.config import ADMIN_TG_IDS
from app.db import get_session
from app.services import add_admin_audit, set_setting

log = logging.getLogger("zhizhu.admin_roles")

def _patched_admin_id(body=None, user_id: int = 0, init_data: str = "") -> int:
    uid = _uid(body=body, user_id=user_id, init_data=init_data)
    if not uid:
        return 0
    db = get_session()
    try:
        return uid if is_admin_tg(db, uid) else 0
    finally:
        db.close()


def _install_admin_id_patches() -> None:
    """Point chunked/admin helpers at role-aware identity without rewriting big files."""
    targets = [
        "app.admin_routes",
        "app.admin_ops",
        "app.card_admin",
        "app.coupons",
        "app.saas_clones",
        "app.fx_rate",
        "app.inline_tpl_admin",
    ]
    for modname in targets:
        try:
            mod = __import__(modname, fromlist=["*"])
        except Exception as exc:  # noqa: BLE001
            log.warning("wave4 patch skip %s: %s", modname, exc)
            continue
        if hasattr(mod, "_admin_id"):
            setattr(mod, "_admin_id", _patched_admin_id)
        if hasattr(mod, "_admin"):
            setattr(mod, "_admin", _patched_admin_id)


def mount_wave4(app) -> None:
    _install_admin_id_patches()
    from app.wave4_mini_html import install_mini_html_middleware

    install_mini_html_middleware(app)

    @app.middleware("http")
    async def wave4_me_is_admin(request: Request, call_next):
        """Ensure /api/mini/me is_admin reflects settings roles (not only ADMIN_TG_IDS)."""
        response = await call_next(request)
        if request.url.path != "/api/mini/me" or response.status_code != 200:
            return response
        try:
            body = b""
            async for chunk in response.body_iterator:
                body += chunk
            data = json.loads(body.decode() or "{}")
            uid = _uid(
                user_id=int(request.query_params.get("user_id") or 0),
                init_data=request.query_params.get("init_data") or "",
            )
            if uid and isinstance(data, dict) and data.get("ok"):
                db = get_session()
                try:
                    data["is_admin"] = bool(is_admin_tg(db, uid))
                    if data["is_admin"]:
                        data["admin_role"] = role_of(db, uid)
                finally:
                    db.close()
                return JSONResponse(data, status_code=200)
            return JSONResponse(data, status_code=response.status_code)
        except Exception as exc:  # noqa: BLE001
            log.warning("wave4 me patch failed: %s", exc)
            return response

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
    async def wave4_guards(request: Request, call_next):
        path = request.url.path or ""
        client = request.client.host if request.client else "unknown"

        if request.method == "POST" and (
            path.startswith("/api/mini/admin")
            or path
            in {
                "/api/mini/coupon/redeem",
                "/api/mini/profile",
                "/api/mini/order",
                "/api/mini/stars-paid",
                "/api/mini/cancel",
            }
        ):
            if not _admin_rl.allow(f"mut:{client}:{path}", limit=40, window_sec=60):
                return JSONResponse({"error": "请求过快，请稍后再试"}, status_code=429)

        if request.method == "GET" and path in {
            "/api/mini/lookup",
            "/api/mini/plans",
            "/api/mini/pending",
            "/api/mini/me",
            "/api/mini/orders",
        }:
            if not _public_rl.allow(f"pub:{client}:{path}", limit=90, window_sec=60):
                return JSONResponse({"error": "请求过快，请稍后再试"}, status_code=429)

        need_cap = None
        body_bytes = b""
        if path == "/api/mini/admin" and request.method == "POST":
            body_bytes = await request.body()
            try:
                payload = json.loads(body_bytes.decode() or "{}")
            except json.JSONDecodeError:
                payload = {}
            action = str(payload.get("action") or "")
            need_cap = ACTION_CAP.get(action, "view")
            uid = _uid(body=payload)
        elif path in PATH_CAP and request.method in {"GET", "POST"}:
            if request.method == "POST":
                body_bytes = await request.body()
                try:
                    payload = json.loads(body_bytes.decode() or "{}")
                except json.JSONDecodeError:
                    payload = {}
                uid = _uid(body=payload)
            else:
                uid = _uid(
                    user_id=int(request.query_params.get("user_id") or 0),
                    init_data=request.query_params.get("init_data") or "",
                )
                payload = {}
            need_cap = PATH_CAP[path]
        else:
            uid = 0
            payload = {}

        if need_cap and uid:
            db = get_session()
            try:
                err = assert_cap(db, uid, need_cap)
                if err:
                    return JSONResponse({"error": err}, status_code=403)
            finally:
                db.close()

            if body_bytes:
                async def receive():
                    return {"type": "http.request", "body": body_bytes, "more_body": False}

                request = StarletteRequest(request.scope, receive)

        return await call_next(request)
