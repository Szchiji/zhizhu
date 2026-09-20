"""Pytest bootstrap: sqlite + empty bot token before app imports."""
from __future__ import annotations

import os
import tempfile

_fd, _path = tempfile.mkstemp(suffix=".sqlite3")
os.close(_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_path}"
os.environ["PLATFORM_BOT_TOKEN"] = ""
os.environ.setdefault("USDT_CONFIRM_SECRET", "test-usdt-secret")
os.environ.setdefault("WEBHOOK_SECRET", "test-webhook-secret")
