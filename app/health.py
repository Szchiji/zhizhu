"""Deeper /healthz payload: db, redis (if configured), last USDT check age."""
from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy import text

from app.config import REDIS_URL
from app.db import get_session

log = logging.getLogger("zhizhu.health")


def _db_ok() -> tuple[bool, str]:
    db = get_session()
    try:
        db.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:120]
    finally:
        db.close()


def _redis_status() -> dict[str, Any]:
    url = (REDIS_URL or "").strip()
    if not url:
        return {"configured": False, "ok": None}
    try:
        import redis

        r = redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=1.5)
        r.ping()
        return {"configured": True, "ok": True}
    except Exception as exc:  # noqa: BLE001
        return {"configured": True, "ok": False, "error": str(exc)[:120]}


def _usdt_check_age() -> dict[str, Any]:
    try:
        from app import usdt_watch

        ts = getattr(usdt_watch, "LAST_CHECK_AT", None)
        if not ts:
            return {"last_check_at": None, "age_sec": None}
        age = max(0.0, time.time() - float(ts))
        return {"last_check_at": float(ts), "age_sec": round(age, 1)}
    except Exception as exc:  # noqa: BLE001
        return {"last_check_at": None, "age_sec": None, "error": str(exc)[:80]}


async def health_payload() -> dict[str, Any]:
    db_ok, db_detail = _db_ok()
    redis_info = _redis_status()
    usdt = _usdt_check_age()
    ok = bool(db_ok)
    if redis_info.get("configured") and redis_info.get("ok") is False:
        # Redis misconfig is degraded, not hard-fail (app falls back to memory)
        pass
    return {
        "ok": ok,
        "db": {"ok": db_ok, "detail": db_detail if not db_ok else "ok"},
        "redis": redis_info,
        "usdt_watch": usdt,
    }
