"""Render mini.html with cache-bust + confirm overlay (wave4)."""
from __future__ import annotations

import json

from fastapi.responses import HTMLResponse


def render_mini_html(*, templates, request, db, plans, plan_stars, plan_usdt) -> HTMLResponse:
    ctx = {
        "request": request,
        "stars": plan_stars(db, "year"),
        "usdt": f"{plan_usdt(db, 'year'):g}",
        "plans_json": json.dumps(plans, ensure_ascii=False).replace("<", "\u003c"),
    }
    html = templates.get_template("mini.html").render(ctx)
    html = html.replace("?v=12", "?v=13")
    if "mini-confirm.js" not in html:
        html = html.replace(
            "</body>",
            '<script src="/mini-confirm.js?v=13"></script></body>',
        )
    out = HTMLResponse(html)
    out.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    out.headers["Pragma"] = "no-cache"
    return out
