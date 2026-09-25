"""Admin API + static serve for inline title/description templates."""
from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.responses import FileResponse, JSONResponse, Response

from app.config import ADMIN_TG_IDS
from app.db import get_session
from app.inline_tpl import load_tpl, save_tpl
from app.services import add_admin_audit
from app.tg_webapp import require_webapp_user

JS_PATH = Path(__file__).resolve().parent / "templates" / "mini-inline.js"


def _admin(body=None, user_id: int = 0, init_data: str = "") -> int:
    del user_id
    uid = require_webapp_user(init_data=init_data, body=body)
    return uid if uid in ADMIN_TG_IDS else 0


def mount_inline_tpl_admin(app) -> None:
    @app.get("/mini-inline.js")
    async def mini_inline_js():
        if JS_PATH.exists():
            return FileResponse(JS_PATH, media_type="text/javascript; charset=utf-8")
        return Response("console.error('mini-inline.js missing')", media_type="text/javascript")

    @app.get("/api/mini/admin/inline_tpl")
    async def get_inline_tpl(user_id: int = 0, init_data: str = ""):
        if not _admin(user_id=user_id, init_data=init_data):
            return JSONResponse({"error": "仅管理员"}, status_code=403)
        db = get_session()
        try:
            return {"ok": True, "inline_tpl": load_tpl(db)}
        finally:
            db.close()

    @app.post("/api/mini/admin/inline_tpl")
    async def post_inline_tpl(request: Request):
        body = await request.json()
        admin = _admin(body)
        if not admin:
            return JSONResponse({"error": "仅管理员"}, status_code=403)
        db = get_session()
        try:
            data = save_tpl(db, body)
            add_admin_audit(
                db,
                admin,
                "inline_tpl_save",
                target_type="inline_tpl",
                target_id="inline",
                detail="save_tpl",
            )
            db.commit()
            return {"ok": True, "inline_tpl": load_tpl(db)}
        finally:
            db.close()
