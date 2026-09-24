"""Wave5: static ver + onboarding flags."""
from __future__ import annotations

from app.static_ver import MINI_ASSET_VER
from app.wave5_onboarding import need_onboarding, profile_incomplete


def test_mini_asset_ver_bumped():
    assert isinstance(MINI_ASSET_VER, int)
    assert MINI_ASSET_VER >= 14


def test_profile_incomplete_logic():
    class I:
        display_name = ""
        username = ""

    assert profile_incomplete(None) is True
    assert profile_incomplete(I()) is True
    I.display_name = "甲"
    assert profile_incomplete(I()) is True
    I.username = "alice"
    assert profile_incomplete(I()) is False


def test_wave5_wired_in_routes():
    from pathlib import Path

    text = Path("app/admin_routes.py").read_text(encoding="utf-8")
    assert "mount_wave5" in text
    html_mw = Path("app/wave4_mini_html.py").read_text(encoding="utf-8")
    assert "MINI_ASSET_VER" in html_mw
    assert "mini-onboard.js" in html_mw
