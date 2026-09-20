from __future__ import annotations

import hashlib
import hmac
import json
from urllib.parse import parse_qsl

from app.config import PLATFORM_BOT_TOKEN


def _pairs(init_data: str) -> dict[str, str]:
    if not init_data or not PLATFORM_BOT_TOKEN:
        return {}
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    got = pairs.pop("hash", "")
    if not got:
        return {}
    data_check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", PLATFORM_BOT_TOKEN.encode(), hashlib.sha256).digest()
    expect = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expect, got):
        return {}
    return pairs


def user_from_init(init_data: str) -> dict:
    pairs = _pairs(init_data)
    if not pairs:
        return {}
    try:
        user = json.loads(pairs.get("user") or "{}") or {}
    except Exception:
        return {}
    first = str(user.get("first_name") or "").strip()
    last = str(user.get("last_name") or "").strip()
    return {
        "id": int(user.get("id") or 0),
        "username": str(user.get("username") or "").lstrip("@"),
        "full_name": " ".join(x for x in (first, last) if x),
    }


def user_id_from_init(init_data: str) -> int:
    return int(user_from_init(init_data).get("id") or 0)


def require_webapp_user(init_data: str = "", body: dict | None = None) -> int:
    """Return Telegram user id only from HMAC-verified WebApp init_data.

    Never trusts client-supplied bare user_id. Returns 0 when init_data is
    missing or fails verification (callers should respond 401).
    """
    raw = (init_data or "").strip()
    if not raw and body is not None:
        raw = str(body.get("init_data") or "").strip()
    if not raw:
        return 0
    return user_id_from_init(raw)
