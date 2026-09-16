from __future__ import annotations

import hashlib
import hmac
from urllib.parse import parse_qsl

from app.config import PLATFORM_BOT_TOKEN


def user_id_from_init(init_data: str) -> int:
    if not init_data or not PLATFORM_BOT_TOKEN:
        return 0
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    got = pairs.pop("hash", "")
    if not got:
        return 0
    data_check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", PLATFORM_BOT_TOKEN.encode(), hashlib.sha256).digest()
    expect = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expect, got):
        return 0
    import json

    try:
        return int((json.loads(pairs.get("user") or "{}") or {}).get("id") or 0)
    except Exception:
        return 0
