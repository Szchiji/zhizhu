"""Wave9: serve mini-fx.js (and keep reconcile/ops already served by card_admin)."""
from __future__ import annotations

from pathlib import Path

from fastapi.responses import FileResponse, Response

JS_FX = Path(__file__).resolve().parent / "templates" / "mini-fx.js"
JS_RECONCILE = Path(__file__).resolve().parent / "templates" / "mini-reconcile.js"


def mount_wave9_assets(app) -> None:
    @app.get("/mini-fx.js")
    async def mini_fx_js():
        if JS_FX.exists():
            return FileResponse(JS_FX, media_type="text/javascript; charset=utf-8")
        return Response("console.error('mini-fx.js missing')", media_type="text/javascript")

    # Re-bind reconcile in case older deploy missed card_admin route (idempotent path).
    @app.get("/mini-reconcile.js")
    async def mini_reconcile_js_wave9():
        if JS_RECONCILE.exists():
            return FileResponse(JS_RECONCILE, media_type="text/javascript; charset=utf-8")
        return Response("console.error('mini-reconcile.js missing')", media_type="text/javascript")
