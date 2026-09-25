"""Wave9: serve mini-fx / reconcile-actions / ops-stars JS."""
from __future__ import annotations

from pathlib import Path

from fastapi.responses import FileResponse, Response

T = Path(__file__).resolve().parent / "templates"
FILES = {
    "/mini-fx.js": T / "mini-fx.js",
    "/mini-reconcile-actions.js": T / "mini-reconcile-actions.js",
    "/mini-ops-stars.js": T / "mini-ops-stars.js",
}


def mount_wave9_assets(app) -> None:
    for route, path in FILES.items():

        def _make(p=path, r=route):
            async def _serve():
                if p.exists():
                    return FileResponse(p, media_type="text/javascript; charset=utf-8")
                return Response(f"console.error('{r} missing')", media_type="text/javascript")

            return _serve

        app.add_api_route(route, _make(), methods=["GET"])
