from __future__ import annotations

import html
import json
import logging
import re
import time

from app.brand import brand_name, bot_username

log = logging.getLogger("zhizhu.card_tpl")

KEYS = ("paid", "unpaid", "issuer")
PACKS = ("official", "brief", "pass")
# Telegram Bot API HTML subset (https://core.telegram.org/bots/api#html-style)
TG_TAGS = ("b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "code", "pre", "a")
FOOT = (
    "〇 登记方：本平台（@{机器人}）\n"
    "〇 效力：以实时查询为准；平台可撤销登记\n"
    "〇 谨防仿冒：只认本机器人实时查询结果\n"
    "〇 查询：任意输入框输入  @{机器人} + 用户名\n"
    "〇 申请登记：点下方「开通平台登记」"
)

DEFAULTS = {
    "pack": "official",
    "parse": "html",
    "paid": (
        "🛡️ {品牌} 平台登记身份\n"
        "来源：@{机器人}\n"
        "━━━━━━━━━━━━\n"
        "姓名：{姓名}\n"
        "账号：{账号}\n"
        "ID：{ID}\n"
        "有效期：{有效期}\n"
        "━━━━━━━━━━━━\n"
        "{正文}\n"
        + FOOT
    ),
    "unpaid": (
        "🛡️ {品牌} 平台登记查询\n"
        "来源：@{机器人}\n"
        "━━━━━━━━━━━━\n"
        "{查询词} 尚未完成平台登记\n"
        "本机器人暂无该账号的有效资料\n"
        "━━━━━━━━━━━━\n"
        + FOOT
    ),
    "issuer": (
        "🛡️ {品牌} 平台出具方\n"
        "来源：@{机器人}\n"
        "━━━━━━━━━━━━\n"
        "本账号为平台登记机器人\n"
        "负责出具平台登记卡，不是个人身份登记\n"
        "登记可由平台撤销，以实时查询为准\n"
        "━━━━━━━━━━━━\n"
        "〇 查个人请输入：@{机器人} + 对方用户名\n"
        "〇 申请登记：点下方「开通平台登记」"
    ),
}

PACK_BODIES = {
    "official": {k: DEFAULTS[k] for k in KEYS},
    "brief": {
        "paid": "✅ {品牌} 平台登记\n@{机器人}\n\n{姓名}\n{账号}\nID {ID}\n有效期 {有效期}\n\n{正文}\n" + FOOT,
        "unpaid": "{品牌} 查询结果\n\n{查询词} 尚未登记\n暂无有效资料\n" + FOOT,
        "issuer": "🛡️ {品牌} 出具方\n@{机器人}\n\n本账号出具平台登记卡，不是个人登记\n效力以实时查询为准，平台可撤销\n〇 查个人：@{机器人} + 用户名",
    },
    "pass": {
        "paid": "🛡️ {品牌}\n平台登记身份\n\n姓名\t{姓名}\n账号\t{账号}\n编号\t{ID}\n\n{正文}\n〇 以 @{机器人} 实时查询为准；平台可撤销",
        "unpaid": "🛡️ {品牌}\n未找到平台登记\n\n查询对象\t{查询词}\n" + FOOT,
        "issuer": "🛡️ {品牌}\n平台出具方\n\n账号\t@{机器人}\n性质\t登记机器人\n〇 查个人：@{机器人} + 用户名",
    },
}

_TAG_RE = re.compile(r"</?\s*([a-zA-Z0-9]+)(\s[^>]*)?>", re.I)
_A_OPEN_RE = re.compile(r'<a\s+[^>]*href\s*=\s*([\'"])(.*?)\1[^>]*>', re.I)


def sanitize_telegram_html(text: str) -> str:
    """Keep only Telegram-allowed HTML tags; drop others. Placeholders like {姓名} stay intact."""
    if not text:
        return ""
    out = []
    pos = 0
    for m in _TAG_RE.finditer(text):
        out.append(text[pos:m.start()])
        name = (m.group(1) or "").lower()
        raw = m.group(0)
        if name not in TG_TAGS:
            # drop disallowed tag, keep inner text flow
            pos = m.end()
            continue
        if name == "a":
            if raw.startswith("</"):
                out.append("</a>")
            else:
                hm = _A_OPEN_RE.match(raw)
                href = (hm.group(2) if hm else "").strip()
                if href.startswith(("http://", "https://", "tg://")):
                    out.append(f'<a href="{html.escape(href, quote=True)}">')
                else:
                    # bad href — skip tag
                    pass
            pos = m.end()
            continue
        # normalize aliases to Telegram's preferred short tags
        norm = {"strong": "b", "em": "i", "ins": "u", "strike": "s", "del": "s"}.get(name, name)
        out.append(f"</{norm}>" if raw.startswith("</") else f"<{norm}>")
        pos = m.end()
    out.append(text[pos:])
    return "".join(out)


def _plain_defaults() -> dict:
    return {k: DEFAULTS[k] for k in ("pack", "parse", *KEYS)}


def load_tpl(db) -> dict:
    data = _plain_defaults()
    if db is None:
        return data
    from app.services import get_setting

    raw = get_setting(db, "card_tpl", "")
    extra = {}
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                extra = parsed
        except Exception:
            extra = {}
    if extra.get("pack") in PACKS:
        data["pack"] = extra["pack"]
    if extra.get("parse") in {"html", "plain"}:
        data["parse"] = extra["parse"]
    for key in KEYS:
        # Prefer per-field keys (survive partial JSON issues), else JSON blob, else default.
        piece = get_setting(db, f"card_tpl_{key}", "")
        if not (isinstance(piece, str) and piece.strip()):
            piece = extra.get(key) or ""
        if isinstance(piece, str) and piece.strip():
            data[key] = piece[:2500]
    return data


def save_tpl(db, body: dict) -> dict:
    """Persist card templates atomically (JSON + per-field keys + rev) in one commit."""
    from app.services import set_setting

    pack = str(body.get("pack") or "official")
    if pack not in PACKS:
        pack = "official"
    if body.get("apply_pack"):
        data = {"pack": pack, "parse": "html", **{k: PACK_BODIES[pack][k] for k in KEYS}}
    else:
        data = load_tpl(db)
        data["pack"] = pack
        data["parse"] = "plain" if str(body.get("parse") or "html") == "plain" else "html"
        for key in KEYS:
            if isinstance(body.get(key), str):
                cleaned = sanitize_telegram_html((body[key] or "").strip())[:2500]
                data[key] = cleaned or DEFAULTS[key]
    blob = json.dumps(data, ensure_ascii=False)
    set_setting(db, "card_tpl", blob, commit=False)
    for key in KEYS:
        set_setting(db, f"card_tpl_{key}", data[key], commit=False)
    set_setting(db, "card_tpl_rev", str(int(time.time())), commit=False)
    db.commit()
    return data


def apply_pack(db, pack: str) -> dict:
    if pack not in PACKS:
        pack = "official"
    return save_tpl(db, {"pack": pack, "apply_pack": True})


def parse_mode_for(db=None) -> str | None:
    """Telegram parse_mode for outgoing cards. None = plain text."""
    tpl = load_tpl(db)
    return "HTML" if tpl.get("parse") != "plain" else None


def _ctx(extra: dict | None = None) -> dict:
    bot = bot_username()
    data = {
        "品牌": brand_name(),
        "机器人": bot,
        "bot": bot,
        "姓名": "—",
        "账号": "未绑定",
        "ID": "—",
        "正文": "",
        "查询词": "",
        "有效期": "—",
    }
    if extra:
        data.update({k: v for k, v in extra.items() if v is not None})
    return data


def fill(text: str, extra: dict | None = None) -> str:
    """Fill placeholders. Dynamic values are HTML-escaped so user fields
    (姓名/账号/正文/查询词/…) cannot inject Telegram HTML markup.
    Static template text is left intact for intentional admin formatting
    (sanitized on save to the Telegram HTML subset).
    """
    out = text or ""
    for key, value in _ctx(extra).items():
        raw = "" if value is None else str(value)
        # Telegram HTML: escape <>& in substituted values only.
        safe = html.escape(raw, quote=False)
        out = out.replace("{" + key + "}", safe)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def render(kind: str, extra: dict | None = None, db=None) -> str:
    close = False
    if db is None:
        try:
            from app.db import get_session

            db = get_session()
            close = True
        except Exception:
            log.exception("card_tpl.render: get_session failed; using defaults")
            db = None
    try:
        tpl = load_tpl(db)
        body = tpl.get(kind) or DEFAULTS.get(kind) or DEFAULTS["unpaid"]
        return fill(body, extra)
    finally:
        if close and db is not None:
            try:
                db.close()
            except Exception:
                pass
