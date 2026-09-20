from __future__ import annotations

import html
import json
import re

from app.brand import brand_name, bot_username

KEYS = ("paid", "unpaid", "issuer")
PACKS = ("official", "brief", "pass")
FOOT = (
    "〇 谨防仿冒：只认本机器人实时查询结果\n"
    "〇 查询：任意输入框输入  @{机器人} + 用户名\n"
    "〇 申请官方卡：点下方「开通官方核验」"
)

DEFAULTS = {
    "pack": "official",
    "parse": "plain",
    "paid": (
        "🛡️ {品牌} 官方核验来源：@{机器人}\n"
        "━━━━━━━━━━━━\n"
        "姓名：{姓名}\n"
        "账号：{账号}\n"
        "ID：{ID}\n"
        "━━━━━━━━━━━━\n"
        "{正文}\n"
        + FOOT
    ),
    "unpaid": (
        "🛡️ {品牌} 官方核验来源：@{机器人}\n"
        "━━━━━━━━━━━━\n"
        "{查询词} 尚未完成官方登记\n"
        "本机器人暂无该账号的有效资料\n"
        "━━━━━━━━━━━━\n"
        + FOOT
    ),
    "issuer": (
        "🛡️ {品牌} 官方出具方\n"
        "来源：@{机器人}\n"
        "━━━━━━━━━━━━\n"
        "本账号为平台核验机器人\n"
        "负责出具官方登记卡，不是个人身份登记\n"
        "━━━━━━━━━━━━\n"
        "〇 查个人请输入：@{机器人} + 对方用户名\n"
        "〇 申请官方卡：点下方「开通官方核验」"
    ),
}

PACK_BODIES = {
    "official": {k: DEFAULTS[k] for k in KEYS},
    "brief": {
        "paid": "✅ {品牌} 官方登记\n@{机器人}\n\n{姓名}\n{账号}\nID {ID}\n\n{正文}\n" + FOOT,
        "unpaid": "{品牌} 查询结果\n\n{查询词} 尚未登记\n暂无有效资料\n" + FOOT,
        "issuer": "🛡️ {品牌} 出具方\n@{机器人}\n\n本账号出具官方登记卡，不是个人登记\n〇 查个人：@{机器人} + 用户名",
    },
    "pass": {
        "paid": "🛡️ {品牌}\n官方身份登记\n\n姓名\t{姓名}\n账号\t{账号}\n编号\t{ID}\n\n{正文}\n〇 以 @{机器人} 实时查询为准",
        "unpaid": "🛡️ {品牌}\n未找到官方登记\n\n查询对象\t{查询词}\n" + FOOT,
        "issuer": "🛡️ {品牌}\n平台出具方\n\n账号\t@{机器人}\n性质\t核验机器人\n〇 查个人：@{机器人} + 用户名",
    },
}


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
        piece = get_setting(db, f"card_tpl_{key}", "") or extra.get(key) or ""
        if isinstance(piece, str) and piece.strip():
            data[key] = piece[:2500]
    return data


def save_tpl(db, body: dict) -> dict:
    from app.services import set_setting
    pack = str(body.get("pack") or "official")
    if pack not in PACKS:
        pack = "official"
    if body.get("apply_pack"):
        data = {"pack": pack, "parse": "plain", **PACK_BODIES[pack]}
    else:
        data = load_tpl(db)
        data["pack"] = pack
        data["parse"] = "plain" if str(body.get("parse") or "plain") != "html" else "html"
        for key in KEYS:
            if isinstance(body.get(key), str):
                data[key] = (body[key] or "").strip()[:2500] or DEFAULTS[key]
    blob = json.dumps(data, ensure_ascii=False)
    set_setting(db, "card_tpl", blob)
    for key in KEYS:
        set_setting(db, f"card_tpl_{key}", data[key])
    set_setting(db, "card_tpl_rev", str(int(__import__("time").time())))
    return data


def apply_pack(db, pack: str) -> dict:
    if pack not in PACKS:
        pack = "official"
    return save_tpl(db, {"pack": pack, "apply_pack": True})


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
    }
    if extra:
        data.update({k: v for k, v in extra.items() if v is not None})
    return data


def fill(text: str, extra: dict | None = None) -> str:
    """Fill placeholders. Dynamic values are HTML-escaped so user fields
    (姓名/账号/正文/查询词/…) cannot inject Telegram HTML markup.
    Static template text is left intact for intentional admin formatting.
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
            db = None
    try:
        tpl = load_tpl(db)
        body = tpl.get(kind) or DEFAULTS.get(kind) or DEFAULTS["unpaid"]
        return fill(body, extra)
    finally:
        if close and db is not None:
            db.close()
