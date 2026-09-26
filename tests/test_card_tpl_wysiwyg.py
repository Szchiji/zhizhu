"""Card template WYSIWYG + scoped emoji bars (MINI_ASSET_VER >= 20)."""
from __future__ import annotations

import base64
import re
import zlib
from pathlib import Path

from app.static_ver import MINI_ASSET_VER

ROOT = Path(__file__).resolve().parents[1]


def _maybe_inflate_js(text: str) -> str:
    """Support deflate+atob bootstrap used when MCP payloads must stay small."""
    if "DecompressionStream('deflate')" not in text or "atob(" not in text:
        return text
    m = re.search(r"atob\('([^']+)'\)", text)
    if not m:
        return text
    return zlib.decompress(base64.b64decode(m.group(1))).decode("utf-8")


def test_mini_asset_ver_wysiwyg():
    assert isinstance(MINI_ASSET_VER, int)
    assert MINI_ASSET_VER >= 20


def test_mini_ui_scoped_emobar_and_wysiwyg():
    raw = (ROOT / "app/templates/mini-ui.js").read_text(encoding="utf-8")
    ui = _maybe_inflate_js(raw)
    assert "syncVisToTa" in ui
    assert "paintAllVisFromTa" in ui
    assert "ownPh" in ui
    assert "querySelector('.phbar')" not in ui
    assert "已登记卡 · 自定义表情" in ui
    assert "未登记卡 · 自定义表情" in ui
    assert "出具方卡 · 自定义表情" in ui


def test_mini_html_visual_editors():
    html = (ROOT / "app/templates/mini.html").read_text(encoding="utf-8")
    assert 'id="ctpaid-vis"' in html
    assert 'id="ctunpaid-vis"' in html
    assert 'id="ctissuer-vis"' in html
    assert "tpl-src" in html
    assert ".tpl-vis" in html
    assert "所见即所得" in html
    assert "编辑的是 Telegram HTML 源码" not in html
