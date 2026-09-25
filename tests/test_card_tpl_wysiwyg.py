"""Card template WYSIWYG editor + scoped emoji bars (MINI_ASSET_VER >= 20)."""
from __future__ import annotations

from pathlib import Path

from app.static_ver import MINI_ASSET_VER


ROOT = Path(__file__).resolve().parents[1]


def test_mini_asset_ver_wysiwyg():
    assert isinstance(MINI_ASSET_VER, int)
    assert MINI_ASSET_VER >= 20


def test_mini_ui_has_scoped_emobar_and_wysiwyg():
    ui = (ROOT / "app/templates/mini-ui.js").read_text(encoding="utf-8")
    assert "contenteditable" in ui
    assert "visEditors" in ui
    assert "paintAllVisFromTa" in ui
    assert "syncAllVisToTa" in ui
    assert "ownPh" in ui
    assert "已登记卡 · 自定义表情" in ui
    assert "未登记卡 · 自定义表情" in ui
    assert "出具方卡 · 自定义表情" in ui
    assert "querySelector('.phbar')" not in ui


def test_mini_html_wysiwyg_hint_and_surfaces():
    html = (ROOT / "app/templates/mini.html").read_text(encoding="utf-8")
    assert "所见即所得" in html
    assert "编辑的是 Telegram HTML" not in html
    assert 'id="ctpaid-vis"' in html
    assert 'id="ctunpaid-vis"' in html
    assert 'id="ctissuer-vis"' in html
    assert "tpl-src" in html and "tpl-vis" in html


def test_mini_js_emobar_scoped_if_present():
    """Legacy mini.js still duplicates mountTgBars — keep emoji insert scoped."""
    p = ROOT / "app/templates/mini.js"
    if not p.exists():
        return
    js = p.read_text(encoding="utf-8")
    if "emobar" not in js:
        return
    assert "querySelector('.phbar')" not in js
    assert "已登记卡 · 自定义表情" in js
