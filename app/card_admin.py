from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.responses import FileResponse, JSONResponse, Response

from app.card_tpl import apply_pack, load_tpl, save_tpl
from app.config import ADMIN_TG_IDS
from app.db import get_session
from app.tg_webapp import user_id_from_init

JS_PATH = Path(__file__).resolve().parent / "templates" / "mini.js"


def _admin(body=None, user_id: int = 0, init_data: str = "") -> int:
    uid = 0
    if init_data:
        uid = user_id_from_init(init_data)
    if not uid and body:
        uid = user_id_from_init(str(body.get("init_data") or ""))
        if not uid:
            try:
                uid = int(body.get("user_id") or 0)
            except (TypeError, ValueError):
                uid = 0
    if not uid:
        uid = int(user_id or 0)
    return uid if uid in ADMIN_TG_IDS else 0


def mount_card_admin(app) -> None:
    @app.get("/mini.js")
    async def mini_js():
        if JS_PATH.exists():
            return FileResponse(JS_PATH, media_type="text/javascript; charset=utf-8")
        return Response("console.error('mini.js missing')", media_type="text/javascript")

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
        if not _admin(body):
            return JSONResponse({"error": "仅管理员"}, status_code=403)
        db = get_session()
        try:
            if body.get("apply_pack") or body.get("action") == "pack":
                data = apply_pack(db, str(body.get("pack") or "official"))
            else:
                data = save_tpl(db, body)
            return {"ok": True, "card_tpl": data}
        finally:
            db.close()
