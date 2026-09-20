from __future__ import annotations

import html
import json
import re

from app.brand import brand_name, bot_username

KEYS = ("paid", "unpaid", "issuer")
PACKS = ("official", "brief", "pass")

DEFAULTS = {
    "pack": "official",
    "parse": "html",
    "paid": (
        "🛡️ {品牌} 官方核验来源：@{机器人}\n"
        "━━━━━━━━━━━━\n"
        "姓名：{姓名}\n"
        "账号：{账号}\n"
        "ID：{ID}\n"
        "━━━━━━━━━━━━\n"
        "{正文}\n"
        "<blockquote>谨防仿冒：只认本机器人实时查询结果\n"
        "查询：任意输入框输入  @{机器人} + 用户名\n"
        "申请官方卡：点下方「开通官方核验」</blockquote>"
    ),
    "unpaid": (
        "🛡️ {品牌} 官方核验来源：@{机器人}\n"
        "━━━━━━━━━━━━\n"
        "{查询词} 尚未完成官方登记\n"
        "本机器人暂无该账号的有效资料\n"
        "━━━━━━━━━━━━\n"
        "<blockquote>谨防仿冒：只认本机器人实时查询结果\n"
        "查询：任意输入框输入  @{机器人} + 用户名\n"
        "申请官方卡：点下方「开通官方核验」</blockquote>"
    ),
    "issuer": (
        "🛡️ {品牌} 官方出具方\n"
        "来源：@{机器人}\n"
        "━━━━━━━━━━━━\n"
        "本账号为平台核验机器人\n"
        "负责出具官方登记卡，不是个人身份登记\n"
        "━━━━━━━━━━━━\n"
        "<blockquote>查个人请输入：@{机器人} + 对方用户名\n"
        "申请官方卡：点下方「开通官方核验」</blockquote>"
    ),
}

PACK_BODIES = {
    "official": {k: DEFAULTS[k] for k in KEYS},
    "brief": {
        "paid": (
            "✅ {品牌} 官方登记\n"
            "@{机器人}\n\n"
            "{姓名}\n{账号}\nID {ID}\n\n"
            "{正文}\n"
            "<blockquote>查询 @{机器人} + 用户名 · 申请点下方开通</blockquote>"
        ),
        "unpaid": (
            "{品牌} 查询结果\n\n"
            "{查询词} 尚未登记\n"
            "暂无有效资料\n"
            "<blockquote>查询 @{机器人} + 用户名 · 申请点下方开通</blockquote>"
        ),
        "issuer": (
            "🛡️ {品牌} 出具方\n@{机器人}\n\n"
            "本账号出具官方登记卡，不是个人登记\n"
            "<blockquote>查个人：@{机器人} + 用户名</blockquote>"
        ),
    },
    "pass": {
        "paid": (
            "🛡️ {品牌}\n"
            "官方身份登记\n\n"
            "姓名\t{姓名}\n"
            "账号\t{账号}\n"
            "编号\t{ID}\n\n"
            "{正文}\n"
            "<blockquote>以 @{机器人} 实时查询为准</blockquote>"
        ),
        "unpaid": (
            "🛡️ {品牌}\n"
            "未找到官方登记\n\n"
            "查询对象\t{查询词}\n"
            "<blockquote>申请官方卡：点下方开通</blockquote>"
        ),
        "issuer": (
            "🛡️ {品牌}\n"
            "平台出具方\n\n"
            "账号\t@{机器人}\n"
            "性质\t核验机器人\n"
            "<blockquote>查个人：@{机器人} + 用户名</blockquote>"
        ),
    },
}

_ALLOWED = re.compile(
    r"</?(?:b|strong|i|em|u|s|code|pre|blockquote)(?:\s+expandable)?\s*>|"
    r"<a\s+href=\"[^\"]+\">|</a>",
    re.I,
)


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
        data = {"pack": pack, "parse": "html", **PACK_BODIES[pack]}
    else:
        data = load_tpl(db)
        data["pack"] = pack
        data["parse"] = "html" if str(body.get("parse") or "html") != "plain" else "plain"
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


def _esc(text: str) -> str:
    return html.escape(text or "", quote=False)


def fill(text: str, extra: dict | None = None, *, escape: bool = True) -> str:
    ctx = _ctx(extra)
    out = text or ""
    for key, value in ctx.items():
        token = "{" + key + "}"
        raw = "" if value is None else str(value)
        out = out.replace(token, _esc(raw) if escape else raw)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    if escape:
        # keep only known tags that were in the template, not user values
        pass
    return out


def render(kind: str, extra: dict | None = None, db=None) -> str:
    tpl = load_tpl(db)
    body = tpl.get(kind) or DEFAULTS.get(kind) or DEFAULTS["unpaid"]
    return fill(body, extra, escape=True)
