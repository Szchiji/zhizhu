"""Configurable Telegram inline-query title/description (subtitle) templates.

Plain text only (no HTML parse_mode on title/description). Defaults match the
historical hardcodes in inline_query.py / tenant_bot.py so empty settings keep
identical UX.
"""
from __future__ import annotations

import json
import logging
import re
import time

from app.brand import brand_name, bot_username

log = logging.getLogger("zhizhu.inline_tpl")

KINDS = ("paid", "unpaid", "issuer", "clone")
FIELDS = ("title", "description")

# Telegram InlineQueryResultArticle limits (practical caps).
TITLE_MAX = 64
DESC_MAX = 100

DEFAULTS: dict[str, dict[str, str]] = {
    "paid": {
        "title": "\u2705 {\u8d26\u53f7} \u5e73\u53f0\u767b\u8bb0",
        "description": "{\u59d3\u540d} \u00b7 ID {ID}",
    },
    "unpaid": {
        "title": "\u67e5\u8be2 @{\u67e5\u8be2\u8bcd}",
        "description": "\u70b9\u51fb\u53d1\u9001\u767b\u8bb0\u5361",
    },
    "issuer": {
        "title": "\U0001f6e1\ufe0f {\u54c1\u724c} \u5e73\u53f0\u51fa\u5177\u65b9",
        "description": "\u672c\u8d26\u53f7\u4e3a\u5e73\u53f0\u767b\u8bb0\u673a\u5668\u4eba",
    },
    "clone": {
        "title": "{\u59d3\u540d} \u00b7 \u767b\u8bb0\u5361",
        "description": "\u53d1\u9001\u5e73\u53f0\u767b\u8bb0\u5361",
    },
}

# Empty inline query (promo) \u2014 not admin-editable; preserves old UX.
EMPTY_UNPAID: dict[str, str] = {
    "title": "{\u54c1\u724c}\u00b7\u5e73\u53f0\u767b\u8bb0",
    "description": "\u8f93\u5165\u7528\u6237\u540d\u67e5\u8be2",
}

_TAG_RE = re.compile(r"<[^>]*>")


def _strip_tags(text: str) -> str:
    """Plain-text sanitize: drop HTML-ish tags and angle brackets."""
    out = _TAG_RE.sub("", text or "")
    return out.replace("<", "").replace(">", "")


def _truncate(text: str, limit: int) -> str:
    s = (text or "").strip()
    if len(s) <= limit:
        return s
    if limit <= 1:
        return s[:limit]
    return s[: limit - 1].rstrip() + "\u2026"


def _plain_defaults() -> dict[str, dict[str, str]]:
    return {k: dict(v) for k, v in DEFAULTS.items()}


def load_tpl(db) -> dict[str, dict[str, str]]:
    data = _plain_defaults()
    if db is None:
        return data
    from app.services import get_setting

    raw = get_setting(db, "inline_tpl", "")
    extra: dict = {}
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                extra = parsed
        except Exception:
            extra = {}
    for kind in KINDS:
        bucket = extra.get(kind) if isinstance(extra.get(kind), dict) else {}
        for field in FIELDS:
            piece = get_setting(db, f"inline_tpl_{kind}_{field}", "")
            if not (isinstance(piece, str) and piece.strip()):
                piece = (bucket.get(field) if isinstance(bucket, dict) else "") or ""
            if isinstance(piece, str) and piece.strip():
                data[kind][field] = _strip_tags(piece)[:200]
    return data


def save_tpl(db, body: dict) -> dict[str, dict[str, str]]:
    """Persist inline title/description templates (JSON + per-field keys)."""
    from app.services import set_setting

    data = load_tpl(db)
    incoming = body.get("inline_tpl") if isinstance(body.get("inline_tpl"), dict) else body
    for kind in KINDS:
        src = incoming.get(kind) if isinstance(incoming.get(kind), dict) else None
        if src is None:
            # flat keys: paid_title / paid_description
            flat_t = incoming.get(f"{kind}_title")
            flat_d = incoming.get(f"{kind}_description")
            if flat_t is None and flat_d is None:
                continue
            src = {}
            if isinstance(flat_t, str):
                src["title"] = flat_t
            if isinstance(flat_d, str):
                src["description"] = flat_d
        for field in FIELDS:
            if isinstance(src.get(field), str):
                cleaned = _strip_tags((src[field] or "").strip())[:200]
                data[kind][field] = cleaned or DEFAULTS[kind][field]
    blob = json.dumps(data, ensure_ascii=False)
    set_setting(db, "inline_tpl", blob, commit=False)
    for kind in KINDS:
        for field in FIELDS:
            set_setting(db, f"inline_tpl_{kind}_{field}", data[kind][field], commit=False)
    set_setting(db, "inline_tpl_rev", str(int(time.time())), commit=False)
    db.commit()
    return data


def _ctx(extra: dict | None = None) -> dict:
    bot = bot_username()
    data = {
        "\u54c1\u724c": brand_name(),
        "\u673a\u5668\u4eba": bot,
        "bot": bot,
        "\u59d3\u540d": "\u2014",
        "\u8d26\u53f7": "\u672a\u7ed1\u5b9a",
        "ID": "\u2014",
        "\u67e5\u8be2\u8bcd": "",
        "\u6709\u6548\u671f": "\u2014",
    }
    if extra:
        data.update({k: v for k, v in extra.items() if v is not None})
    return data


def fill(text: str, extra: dict | None = None) -> str:
    """Fill placeholders. Dynamic values are tag-stripped (plain text titles)."""
    out = text or ""
    for key, value in _ctx(extra).items():
        raw = "" if value is None else str(value)
        safe = _strip_tags(raw)
        out = out.replace("{" + key + "}", safe)
    return out.strip()


def render(kind: str, field: str, extra: dict | None = None, db=None) -> str:
    """Render one title or description field for a kind."""
    close = False
    if field not in FIELDS:
        field = "title"
    if db is None:
        try:
            from app.db import get_session

            db = get_session()
            close = True
        except Exception:
            log.exception("inline_tpl.render: get_session failed; using defaults")
            db = None
    try:
        # Empty unpaid query \u2192 preserve historical promo strings.
        query = ""
        if extra:
            query = str(extra.get("\u67e5\u8be2\u8bcd") or "").strip()
        if kind == "unpaid" and not query:
            body = EMPTY_UNPAID.get(field) or DEFAULTS["unpaid"][field]
        else:
            tpl = load_tpl(db)
            bucket = tpl.get(kind) or DEFAULTS.get(kind) or DEFAULTS["unpaid"]
            body = bucket.get(field) or DEFAULTS.get(kind, {}).get(field) or ""
        out = fill(body, extra)
        if field == "description":
            out = out.strip(" \u00b7")
        limit = TITLE_MAX if field == "title" else DESC_MAX
        return _truncate(out, limit)
    finally:
        if close and db is not None:
            try:
                db.close()
            except Exception:
                pass
