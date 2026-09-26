"""Card template WYSIWYG overlay + scoped emoji bars (MINI_ASSET_VER >= 20)."""
from __future__ import annotations

from pathlib import Path

from app.static_ver import MINI_ASSET_VER
from app.wave_card_wysiwyg import NEW_HINT, OLD_HINT, patch_mini_html


ROOT = Path(__file__).resolve().parents[1]


def test_mini_asset_ver_wysiwyg():
    assert isinstance(MINI_ASSET_VER, int)
    assert MINI_ASSET_VER >= 20


def test_overlay_js_scoped_emobar_and_wysiwyg():
    parts = [ROOT / f"app/templates/mini-card-wysiwyg.part{i}.js" for i in (1, 2, 3)]
    mono = ROOT / "app/templates/mini-card-wysiwyg.js"
    if all(p.exists() for p in parts):
        ui = "".join(p.read_text(encoding="utf-8") for p in parts)
    else:
        ui = mono.read_text(encoding="utf-8")
    assert "contentEditable" in ui
    assert "tpl-vis" in ui
    assert "phbar.parentNode.insertBefore(emobar, phbar.nextSibling)" in ui
    assert "已登记卡 · 自定义表情" in ui
    assert "未登记卡 · 自定义表情" in ui
    assert "出具方卡 · 自定义表情" in ui
    assert "querySelector('.phbar')" not in ui


def test_html_patch_injects_wysiwyg():
    html = (ROOT / "app/templates/mini.html").read_text(encoding="utf-8")
    assert OLD_HINT in html
    out = patch_mini_html(html)
    assert "mini-card-wysiwyg.js" in out
    assert "textarea.tpl-src" in out
    assert NEW_HINT in out
    assert OLD_HINT not in out
    assert 'class="tpl-area tpl-src"' in out


def test_wave4_and_mount_wired():
    w4 = (ROOT / "app/wave4_mini_html.py").read_text(encoding="utf-8")
    assert "patch_mini_html" in w4
    ar = (ROOT / "app/admin_routes.py").read_text(encoding="utf-8")
    assert "mount_card_wysiwyg" in ar
