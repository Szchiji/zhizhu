"""Wave4: /mini HTML cache-bust + confirm script inject middleware."""
from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.static_ver import MINI_ASSET_VER
from app.wave_card_wysiwyg import patch_mini_html

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
            html = html.replace("?v=12", f"?v={MINI_ASSET_VER}")
            html = html.replace("?v=21", f"?v={MINI_ASSET_VER}")
            if "mini-card-api.js" not in html and 'src="/mini-core.js' in html:
                html = html.replace(
                    f'<script src="/mini-core.js?v={MINI_ASSET_VER}"></script>',
                    f'<script src="/mini-card-api.js?v={MINI_ASSET_VER}"></script>'+
                    f'<script src="/mini-core.js?v={MINI_ASSET_VER}"></script>',
                    1,
                )
            if "mini-ui.p0.js" not in html and 'src="/mini-ui.js' in html:
                parts = "".join(
                    f'<script src="/mini-ui.p{i}.js?v={MINI_ASSET_VER}"></script>'
                    for i in range(4)
                )
                html = html.replace(
                    f'<script src="/mini-ui.js?v={MINI_ASSET_VER}"></script>',
                    parts + f'<script src="/mini-ui.js?v={MINI_ASSET_VER}"></script>',
                    1,
                )
            html = patch_mini_html(html)
            extras = (
                "mini-confirm.js",
                "mini-onboard.js",
                "mini-pending.js",
                "mini-ops.js",
                "mini-roles.js",
                "mini-reconcile.js",
                "mini-fx.js",
                "mini-reconcile-actions.js",
                "mini-ops-stars.js",
                "mini-saas.js",
                "mini-inline.js",
            )
            for name in extras:
                if name not in html:
                    html = html.replace(
                        "</body>",
                        f'<script src="/{name}?v={MINI_ASSET_VER}"></script></body>',
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
