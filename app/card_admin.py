from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.responses import FileResponse, JSONResponse, Response

from app.card_tpl import apply_pack, load_tpl, save_tpl
from app.config import ADMIN_TG_IDS
from app.db import get_session
from app.services import add_admin_audit
from app.tg_webapp import require_webapp_user

JS_PATH = Path(__file__).resolve().parent / "templates" / "mini.js"
JS_CORE = Path(__file__).resolve().parent / "templates" / "mini-core.js"
JS_UI = Path(__file__).resolve().parent / "templates" / "mini-ui.js"
JS_CONFIRM = Path(__file__).resolve().parent / "templates" / "mini-confirm.js"
JS_ONBOARD = Path(__file__).resolve().parent / "templates" / "mini-onboard.js"
JS_PENDING = Path(__file__).resolve().parent / "templates" / "mini-pending.js"
JS_OPS = Path(__file__).resolve().parent / "templates" / "mini-ops.js"
JS_ROLES = Path(__file__).resolve().parent / "templates" / "mini-roles.js"


def _admin(body=None, user_id: int = 0, init_data: str = "") -> int:
    """Admin identity from verified WebApp init_data only, then ADMIN_TG_IDS check."""
    del user_id  # never trust client-supplied user_id as proof of identity
    uid = require_webapp_user(init_data=init_data, body=body)
    return uid if uid in ADMIN_TG_IDS else 0


def mount_card_admin(app) -> None:
    @app.get("/mini.js")
    async def mini_js():
        if JS_PATH.exists():
            return FileResponse(JS_PATH, media_type="text/javascript; charset=utf-8")
        return Response("console.error('mini.js missing')", media_type="text/javascript")

    @app.get("/mini-core.js")
    async def mini_core_js():
        if JS_CORE.exists():
            return FileResponse(JS_CORE, media_type="text/javascript; charset=utf-8")
        return Response("console.error('mini-core.js missing')", media_type="text/javascript")

    @app.get("/mini-ui.js")
    async def mini_ui_js():
        if JS_UI.exists():
            return FileResponse(JS_UI, media_type="text/javascript; charset=utf-8")
        return Response("console.error('mini-ui.js missing')", media_type="text/javascript")

    @app.get("/mini-confirm.js")
    async def mini_confirm_js():
        if JS_CONFIRM.exists():
            return FileResponse(JS_CONFIRM, media_type="text/javascript; charset=utf-8")
        return Response("console.error('mini-confirm.js missing')", media_type="text/javascript")

    @app.get("/mini-onboard.js")
    async def mini_onboard_js():
        if JS_ONBOARD.exists():
            return FileResponse(JS_ONBOARD, media_type="text/javascript; charset=utf-8")
        return Response("console.error('mini-onboard.js missing')", media_type="text/javascript")

    @app.get("/mini-pending.js")
    async def mini_pending_js():
        if JS_PENDING.exists():
            return FileResponse(JS_PENDING, media_type="text/javascript; charset=utf-8")
        return Response("console.error('mini-pending.js missing')", media_type="text/javascript")

    @app.get("/mini-ops.js")
    async def mini_ops_js():
        if JS_OPS.exists():
            return FileResponse(JS_OPS, media_type="text/javascript; charset=utf-8")
        return Response("console.error('mini-ops.js missing')", media_type="text/javascript")

    @app.get("/mini-roles.js")
    async def mini_roles_js():
        if JS_ROLES.exists():
            return FileResponse(JS_ROLES, media_type="text/javascript; charset=utf-8")
        return Response("console.error('mini-roles.js missing')", media_type="text/javascript")

    @app.get("/api/mini/admin/card")
    async def get_card(user_id: int = 0, init_data: str = ""):
        if not _admin(user_id=user_id, init_data=init_data):
            return JSONResponse({"error": "仅管理员"}, status_code=403)
        db = get_session()
        try:
            return {"ok": True, "card_tpl": load_tpl(db)}
        finally:
            db.close()

    @app.post("/api/mini/admin/card")
    async def save_card(request: Request):
        body = await request.json()
        admin = _admin(body)
        if not admin:
            return JSONResponse({"error": "仅管理员"}, status_code=403)
        db = get_session()
        try:
            if body.get("apply_pack") or body.get("action") == "pack":
                pack = str(body.get("pack") or "official")
                data = apply_pack(db, pack)
                add_admin_audit(db, admin, "card_pack", target_type="card_tpl", target_id=pack, detail="apply_pack")
            else:
                data = save_tpl(db, body)
                add_admin_audit(db, admin, "card_save", target_type="card_tpl", target_id=str(data.get("pack") or ""), detail="save_tpl")
            # save_tpl already commits settings; commit audit row
            db.commit()
            data = load_tpl(db)
            return {"ok": True, "card_tpl": data}
        finally:
            db.close()
