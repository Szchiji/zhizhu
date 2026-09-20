from __future__ import annotations

import html
import json
import re

from app.brand import brand_name, bot_username

KEYS = ("paid", "unpaid", "issuer")
PACKS = ("official", "brief", "pass")
FOOT = (
    "▍ 谨防仿冒：只认本机器人实时查询结果\n"
    "▍ 查询：任意输入框输入  @{机器人} + 用户名\n"
    "▍ 申请官方卡：点下方「开通官方核验」"
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
        "▍ 查个人请输入：@{机器人} + 对方用户名\n"
        "▍ 申请官方卡：点下方「开通官方核验」"
    ),
}

PACK_BODIES = {
    "official": {k: DEFAULTS[k] for k in KEYS},
    "brief": {
        "paid": "✅ {品牌} 官方登记\n@{机器人}\n\n{姓名}\n{账号}\nID {ID}\n\n{正文}\n" + FOOT,
        "unpaid": "{品牌} 查询结果\n\n{查询词} 尚未登记\n暂无有效资料\n" + FOOT,
        "issuer": "🛡️ {品牌} 出具方\n@{机器人}\n\n本账号出具官方登记卡，不是个人登记\n▍ 查个人：@{机器人} + 用户名",
    },
    "pass": {
        "paid": "🛡️ {品牌}\n官方身份登记\n\
姓名\t{姓名}\n账号\t{账号}\n编号\t{ID}\n\n{正文}\n▍ 以 @{机器人} 实时查询为准",
        "unpaid": "🛡️ {品牌}\n未找到官方登记\n\n查询对象\t{查询词}\n" + FOOT,
        "issuer": "🛡️ {品牌}\n平台出具方\n\n账号\t@{机器人}\n性质\t核验机器人\n▍ 查个人：@{机器人} + 用户名",
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
    if not raw:
        return data
    try:
        extra = json.loads(raw)
    except Exception:
        return data
    if not isinstance(extra, dict):
        return data
    if extra.get("pack") in PACKS:
        data["pack"] = extra["pack"]
    if extra.get("parse") in {"html", "plain"}:
        data["parse"] = extra["parse"]
    for key in KEYS:
        if isinstance(extra.get(key), str) and extra[key].strip():
            data[key] = extra[key][:2500]
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
                data[key] = body[key][:2500] or DEFAULTS[key]
    set_setting(db, "card_tpl", json.dumps(data, ensure_ascii=False))
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
    out = text or ""
    for key, value in _ctx(extra).items():
        raw = "" if value is None else str(value)
        out = out.replace("{" + key + "}", raw)
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
