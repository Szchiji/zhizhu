"""Telegram platform bot.

Implementation lives in plain UTF-8 sibling parts ``_pb_part0.txt`` … ``_pb_part3.txt``
(concatenated in order). Parts are the full readable source, split only to keep
each GitHub Contents upload small.
"""
from __future__ import annotations

from pathlib import Path

_dir = Path(__file__).resolve().parent
_src = "".join((_dir / f"_pb_part{i}.txt").read_text(encoding="utf-8") for i in range(4))
exec(compile(_src, __file__, "exec"), globals())
