"""Wave10: serve mini-saas.js and mount SaaS clone admin APIs."""
from __future__ import annotations

from pathlib import Path

from fastapi.responses import FileResponse, Response

T = Path(__file__).resolve().parent / "templates"


def mount_wave10(app) -> None:
    from app.saas_clones import mount_saas_clones

    mount_saas_clones(app)

    path = T / "mini-saas.js"

    async def _serve():
        if path.exists():
            return FileResponse(path, media_type="text/javascript; charset=utf-8")
        return Response("console.error('/mini-saas.js missing')", media_type="text/javascript")

    app.add_api_route("/mini-saas.js", _serve, methods=["GET"])
