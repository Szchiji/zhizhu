"""Wave4: /mini HTML cache-bust + confirm script inject middleware."""
from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import HTMLResponse

log = logging.getLogger("zhizhu.wave4_mini")


def install_mini_html_middleware(app) -> None:
    @app.middleware("http")
    async def wave4_mini_html(request: Request, call_next):
        response = await call_next(request)
        if request.url.path != "/mini" or response.status_code != 200:
            return response
        try:
            body = b""
            async for chunk in response.body_iterator:
                body += chunk
            html = body.decode("utf-8", errors="replace")
            html = html.replace("?v=12", "?v=13")
            if "mini-confirm.js" not in html:
                html = html.replace(
                    "</body>",
                    '<script src="/mini-confirm.js?v=13"></script></body>',
                )
            return HTMLResponse(
                html,
                status_code=200,
                headers={
                    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                    "Pragma": "no-cache",
                },
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("wave4 mini html patch failed: %s", exc)
            return response
