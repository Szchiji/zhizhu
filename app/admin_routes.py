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
