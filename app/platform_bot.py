"""Telegram platform bot (assembled from plain UTF-8 chunks)."""
from __future__ import annotations

from pathlib import Path

_dir = Path(__file__).resolve().parent
_src = "".join((_dir / f"_pb_c{i}.txt").read_text(encoding="utf-8") for i in range(12))
exec(compile(_src, __file__, "exec"), globals())
