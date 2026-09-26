from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.responses import FileResponse, JSONResponse, Response

from app.card_tpl import apply_pack, load_tpl, save_tpl
from app.config import ADMIN_TG_IDS
from app.db import get_session
from app.services import add_admin_audit
from app.tg_webapp import require_webapp_user

T = Path(__file__).resolve().parent / "templates"
JS_PATH = T / "mini.js"
JS_CORE = T / "mini-core.js"
JS_UI = T / "mini-ui.js"
JS_CARD_API = T / "mini-card-api.js"
JS_CONFIRM = T / "mini-confirm.js"
JS_ONBOARD = T / "mini-onboard.js"
JS_PENDING = T / "mini-pending.js"
JS_OPS = T / "mini-ops.js"
JS_ROLES = T / "mini-roles.js"
JS_RECONCILE = T / "mini-reconcile.js"


def _admin(body=None, user_id: int = 0, init_data: str = "") -> int:
    """Admin identity from verified WebApp init_data only, then ADMIN_TG_IDS check."""
    del user_id
    uid = require_webapp_user(init_data=init_data, body=body)
    return uid if uid in ADMIN_TG_IDS else 0


def _js(path: Path, name: str):
    async def _serve():
        if path.exists():
            return FileResponse(path, media_type="text/javascript; charset=utf-8")
        return Response(f"console.error('{name} missing')", media_type="text/javascript")
    return _serve


def mount_card_admin(app) -> None:
    app.add_api_route("/mini.js", _js(JS_PATH, "mini.js"), methods=["GET"])
    app.add_api_route("/mini-core.js", _js(JS_CORE, "mini-core.js"), methods=["GET"])
    app.add_api_route("/mini-ui.js", _js(JS_UI, "mini-ui.js"), methods=["GET"])
    app.add_api_route("/mini-card-api.js", _js(JS_CARD_API, "mini-card-api.js"), methods=["GET"])
    for i in range(4):
        p = T / f"mini-ui.p{i}.js"
        app.add_api_route(f"/mini-ui.p{i}.js", _js(p, f"mini-ui.p{i}.js"), methods=["GET"])
    app.add_api_route("/mini-confirm.js", _js(JS_CONFIRM, "mini-confirm.js"), methods=["GET"])
    app.add_api_route("/mini-onboard.js", _js(JS_ONBOARD, "mini-onboard.js"), methods=["GET"])
    app.add_api_route("/mini-pending.js", _js(JS_PENDING, "mini-pending.js"), methods=["GET"])
    app.add_api_route("/mini-ops.js", _js(JS_OPS, "mini-ops.js"), methods=["GET"])
    app.add_api_route("/mini-roles.js", _js(JS_ROLES, "mini-roles.js"), methods=["GET"])
    app.add_api_route("/mini-reconcile.js", _js(JS_RECONCILE, "mini-reconcile.js"), methods=["GET"])

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
            db.commit()
            data = load_tpl(db)
            return {"ok": True, "card_tpl": data}
        finally:
            db.close()
