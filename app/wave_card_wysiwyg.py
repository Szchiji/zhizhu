"""Card template WYSIWYG overlay: serve JS + inject CSS/hints into /mini HTML."""
from __future__ import annotations

import base64
import zlib
from pathlib import Path

from fastapi.responses import Response

from app.static_ver import MINI_ASSET_VER

T = Path(__file__).resolve().parent / "templates"
JS = T / "mini-card-wysiwyg.js"
Z64 = T / "mini-card-wysiwyg.js.z64"

CSS = (
    "textarea.tpl-src{display:none!important}"
    ".tpl-vis{min-height:200px;line-height:1.55;font-family:-apple-system,BlinkMacSystemFont,\"Segoe UI\",sans-serif;"
    "font-size:15px;white-space:pre-wrap;word-break:break-word;width:100%;border:1px solid var(--line);"
    "background:#0b0e14;color:var(--text);border-radius:14px;padding:13px 12px;margin-top:8px;outline:none}"
    ".tpl-vis:focus{border-color:rgba(212,175,55,.45)}"
    ".tpl-vis .tg-emoji-chip{display:inline-flex;align-items:center;padding:0 5px;margin:0 1px;border-radius:8px;"
    "background:#1a2110;border:1px solid var(--line);font-size:14px;vertical-align:baseline;user-select:all}"
    ".tpl-vis .ph-token{display:inline;padding:1px 5px;border-radius:6px;background:#151a24;"
    "border:1px dashed rgba(212,175,55,.35);color:var(--gold2);font-size:13px;font-weight:650}"
    ".tpl-vis blockquote{margin:.4em 0;padding-left:10px;border-left:3px solid var(--gold);color:var(--muted)}"
    ".tpl-vis .tg-spoiler{background:#2a2a1a;border-radius:4px;padding:0 2px;color:var(--muted)}"
    ".tpl-vis code{background:#121722;padding:1px 4px;border-radius:4px;font-family:ui-monospace,Menlo,monospace;font-size:13px}"
    ".tpl-vis pre{background:#121722;padding:8px 10px;border-radius:10px;overflow:auto;"
    "font-family:ui-monospace,Menlo,monospace;font-size:12px;white-space:pre-wrap}"
    ".emobar-label{width:100%;font-size:11px;color:var(--muted);margin:2px 0 0}"
)

OLD_HINT = '编辑的是 Telegram HTML 源码；工具栏会插入标签。工具栏：粗体/斜体/下划线/删除线/代码/代码块/链接/引用/可展开/遮罩；可插入占位符与自定义表情（&lt;tg-emoji&gt;，可粘贴 emoji-id）。保存后请重新查询一张卡核对；旧消息不会自动换文案。'
NEW_HINT = '工具栏直接排版，所见即所得；保存后仍按 Telegram 格式发出。工具栏：粗体/斜体/下划线/删除线/代码/代码块/链接/引用/可展开/遮罩；可插入占位符与自定义表情（可粘贴 emoji-id）。保存后请重新查询一张卡核对；旧消息不会自动换文案。'
OLD_SUB = '占位符：{品牌} {机器人} {姓名} {账号} {ID} {正文} {查询词} {有效期}。静态文案可用 Telegram HTML（工具栏一键插入）；用户字段会自动转义。'
NEW_SUB = '占位符：{品牌} {机器人} {姓名} {账号} {ID} {正文} {查询词} {有效期}。工具栏可直接加粗/插表情；用户字段会自动转义。'


def patch_mini_html(html: str) -> str:
    """Inject WYSIWYG CSS, hide card textareas, update hints, load overlay JS."""
    # Inline WYSIWYG already in mini.html + mini-ui.js (syncVisToTa) — skip overlay.
    if 'id="ctpaid-vis"' in html or "syncVisToTa" in html:
        return html
    if "mini-card-wysiwyg.js" not in html:
        html = html.replace(
            "</body>",
            f'<script src="/mini-card-wysiwyg.js?v={MINI_ASSET_VER}"></script></body>',
        )
    if "textarea.tpl-src" not in html:
        html = html.replace("</style>", CSS + "</style>", 1)
    for tid in ("ctpaid", "ctunpaid", "ctissuer"):
        html = html.replace(
            f'<textarea id="{tid}" class="tpl-area"',
            f'<textarea id="{tid}" class="tpl-area tpl-src"',
            1,
        )
    if OLD_HINT in html:
        html = html.replace(OLD_HINT, NEW_HINT, 1)
    if OLD_SUB in html:
        html = html.replace(OLD_SUB, NEW_SUB, 1)
    return html


def _load_wysiwyg_js() -> bytes | None:
    if Z64.exists():
        return zlib.decompress(base64.b64decode(Z64.read_text(encoding="ascii").strip()))
    parts = [T / f"mini-card-wysiwyg.part{i}.js" for i in (1, 2, 3)]
    if all(p.exists() for p in parts):
        return b"".join(p.read_bytes() for p in parts)
    if JS.exists():
        return JS.read_bytes()
    return None


def mount_card_wysiwyg(app) -> None:
    @app.get("/mini-card-wysiwyg.js")
    async def _serve_card_wysiwyg():
        data = _load_wysiwyg_js()
        if data is not None:
            return Response(data, media_type="text/javascript; charset=utf-8")
        return Response(
            "console.error('mini-card-wysiwyg.js missing')",
            media_type="text/javascript",
        )
