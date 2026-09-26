"""Card template WYSIWYG + scoped emoji bars (MINI_ASSET_VER >= 21)."""
from __future__ import annotations

import ast
import base64
import re
import zlib
from pathlib import Path

from app.static_ver import MINI_ASSET_VER

ROOT = Path(__file__).resolve().parents[1]
TPL = ROOT / "app/templates"


def _load_ui_source() -> str:
    """Inflate mini-ui from chunked p0..pN parts or a single atob wrap."""
    parts: list[str] = []
    for i in range(8):
        p = TPL / f"mini-ui.p{i}.js"
        if not p.is_file():
            break
        text = p.read_text(encoding="utf-8")
        m = re.search(r"\.push\((.*)\)\s*;", text)
        if not m:
            raise AssertionError(f"no push() in {p.name}")
        parts.append(ast.literal_eval(m.group(1)))
    if parts:
        return zlib.decompress(base64.b64decode("".join(parts))).decode("utf-8")
    raw = (TPL / "mini-ui.js").read_text(encoding="utf-8")
    if "DecompressionStream" in raw and "atob(" in raw:
        m = re.search(r'atob\(["\']([^"\']+)["\']\)', raw)
        if m:
            return zlib.decompress(base64.b64decode(m.group(1))).decode("utf-8")
    return raw


def test_mini_asset_ver_wysiwyg():
    assert isinstance(MINI_ASSET_VER, int)
    assert MINI_ASSET_VER >= 21


def test_mini_ui_scoped_emobar_and_wysiwyg():
    ui = _load_ui_source()
    assert "syncVisToTa" in ui
    assert "paintAllVisFromTa" in ui
    assert "ownPh" in ui
    assert "querySelector('.phbar')" not in ui
    assert "已登记卡 · 自定义表情" in ui
    assert "未登记卡 · 自定义表情" in ui
    assert "出具方卡 · 自定义表情" in ui


def test_mini_html_visual_editors():
    html = (TPL / "mini.html").read_text(encoding="utf-8")
    assert 'id="ctpaid-vis"' in html
    assert 'id="ctunpaid-vis"' in html
    assert 'id="ctissuer-vis"' in html
    assert "tpl-src" in html
    assert ".tpl-vis" in html
    assert "所见即所得" in html
    assert "编辑的是 Telegram HTML 源码" not in html
    wave4 = (ROOT / "app/wave4_mini_html.py").read_text(encoding="utf-8")
    assert "mini-ui.p0.js" in wave4


def test_mini_ui_self_contained_no_cdn():
    raw = (TPL / "mini-ui.js").read_text(encoding="utf-8")
    assert "jsdelivr" not in raw.lower()
    for i in range(4):
        part = (TPL / f"mini-ui.p{i}.js").read_text(encoding="utf-8")
        assert "jsdelivr" not in part.lower()
    ui = _load_ui_source()
    assert "syncVisToTa" in ui
    assert len(ui) > 5000
