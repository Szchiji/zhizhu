#!/usr/bin/env python3
"""Concatenate chunked admin / platform_bot sources for local review."""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


def assemble_admin() -> str:
    return "".join((APP / f"_admin_r{i}.txt").read_text(encoding="utf-8") for i in range(4))


def assemble_platform_bot() -> str:
    parts = []
    for i in range(12):
        p = APP / f"_pb_c{i}.txt"
        if p.exists():
            parts.append(p.read_text(encoding="utf-8"))
    return "".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("which", choices=("admin", "platform_bot"))
    args = ap.parse_args()
    text = assemble_admin() if args.which == "admin" else assemble_platform_bot()
    print(text, end="")


if __name__ == "__main__":
    main()
