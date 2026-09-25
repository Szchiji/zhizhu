"""Admin routes (assembled from plain UTF-8 chunks for MCP push size limits)."""
from __future__ import annotations

from pathlib import Path

_dir = Path(__file__).resolve().parent
_src = "".join((_dir / f"_admin_r{i}.txt").read_text(encoding="utf-8") for i in range(4))
exec(compile(_src, __file__, "exec"), globals())

_orig_mount_admin = mount_admin


def mount_admin(app):
    _orig_mount_admin(app)
    from app.wave2_pending import mount_wave2_pending

    mount_wave2_pending(app)
    from app.coupons import mount_wave3

    mount_wave3(app)
    from app.admin_roles_mount import mount_wave4

    mount_wave4(app)
    from app.wave5_onboarding import mount_wave5

    mount_wave5(app)
    from app.wave6_settings_export import mount_wave6

    mount_wave6(app)
    from app.fx_rate import mount_fx_rate

    mount_fx_rate(app)
    from app.wave9_revoke_stars import mount_wave9_revoke

    mount_wave9_revoke(app)
    from app.wave9_assets import mount_wave9_assets

    mount_wave9_assets(app)
    from app.wave10_assets import mount_wave10

    mount_wave10(app)
    from app.inline_tpl_admin import mount_inline_tpl_admin

    mount_inline_tpl_admin(app)
