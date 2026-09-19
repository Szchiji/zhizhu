from __future__ import annotations

import json

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.brand import brand_name, brand_title, bot_username
from app.config import PUBLIC_BASE_URL, WEBHOOK_BASE_URL
from app.services import fmt_until, get_setting, set_setting, tenant_usable

ACTIONS = ("mini", "lookup", "help", "url")

DEFAULT = {
    "title": "",
    "body_unpaid": "在任意输入框输入  @{机器人} + 用户名\n即可查看是否已官方登记。\n\
开通后自动生成资料卡，可在小程序改姓名和正文。",
    "body_paid": "你的官方登记已生效。\n群里输入  @{机器人} + 用户名  即可出卡。\n改资料请点左下角「小程序」。",
    "help": "使用说明\n\n1. 查询：在任意输入框输入 @{机器人} + 用户名\n2. 开通：点「开通 / 续费」打开小程序\n3. 改资料：小程序 → 我的",
    "btns": [
        {"label": "开通 / 续费", "action": "mini", "url": ""},
        {"label": "查询登记", "action": "lookup", "url": ""},
        {"label": "使用说明", "action": "help", "url": ""},
    ],
}


def _shown_bot(bot: str = "") -> str:
    return (bot_username() or bot or "").lstrip("@")


def _mini_url() -> str:
    base = (PUBLIC_BASE_URL or WEBHOOK_BASE_URL or "").rstrip("/")
    return f"{base}/mini?v=3" if base else ""


def load_home(db) -> dict:
    data = {
        "title": DEFAULT["title"],
        "body_unpaid": DEFAULT["body_unpaid"],
        "body_paid": DEFAULT["body_paid"],
        "help": DEFAULT["help"],
        "btns": [dict(x) for x in DEFAULT["btns"]],
    }
    raw = get_setting(db, "home_start", "")
    if not raw:
        return data
    try:
        extra = json.loads(raw)
    except Exception:
        return data
    if not isinstance(extra, dict):
        return data
    for key in ("title", "body_unpaid", "body_paid", "help"):
        if isinstance(extra.get(key), str):
            data[key] = extra[key]
    rows = extra.get("btns")
    if isinstance(rows, list) and rows:
        clean = []
        for row in rows[:3]:
            if not isinstance(row, dict):
                continue
            action = str(row.get("action") or "mini")
            if action not in ACTIONS:
                action = "mini"
            clean.append({
                "label": str(row.get("label") or "按钮")[:18],
                "action": action,
                "url": str(row.get("url") or "")[:200],
            })
        if clean:
            data["btns"] = clean
    return data


def save_home(db, body: dict) -> dict:
    btns = []
    raw_btns = body.get("btns") if isinstance(body.get("btns"), list) else []
    for row in raw_btns[:3]:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label") or "").strip()[:18]
        if not label:
            continue
        action = str(row.get("action") or "mini")
        if action not in ACTIONS:
            action = "mini"
        btns.append({"label": label, "action": action, "url": str(row.get("url") or "").strip()[:200]})
    if not btns:
        btns = [dict(x) for x in DEFAULT["btns"]]
    data = {
        "title": str(body.get("title") or "")[:40],
        "body_unpaid": str(body.get("body_unpaid") or DEFAULT["body_unpaid"])[:500],
        "body_paid": str(body.get("body_paid") or DEFAULT["body_paid"])[:500],
        "help": str(body.get("help") or DEFAULT["help"])[:800],
        "btns": btns,
    }
    set_setting(db, "home_start", json.dumps(data, ensure_ascii=False))
    return data


def fill(text: str, *, bot: str = "", until: str = "", username: str = "", name: str = "") -> str:
    bot = _shown_bot(bot)
    return (
        (text or "")
        .replace("{品牌}", brand_name())
        .replace("{机器人}", bot)
        .replace("{bot}", bot)
        .replace("{到期}", until or "—")
        .replace("{账号}", username or "未绑定")
        .replace("{姓名}", name or "—")
    )


def home_kb(cfg: dict, *, bot: str = "", mini: str = "") -> InlineKeyboardMarkup:
    bot = _shown_bot(bot)
    mini = mini or _mini_url()
    rows: list[list[InlineKeyboardButton]] = []
    for item in cfg.get("btns") or []:
        label = item.get("label") or "按钮"
        action = item.get("action") or "mini"
        if action == "mini":
            if mini.startswith("https://"):
                rows.append([InlineKeyboardButton(label, web_app=WebAppInfo(url=mini))])
            elif bot:
                rows.append([InlineKeyboardButton(label, url=f"https://t.me/{bot}?startapp")])
        elif action == "lookup":
            rows.append([InlineKeyboardButton(label, callback_data="ask_lookup")])
        elif action == "help":
            rows.append([InlineKeyboardButton(label, callback_data="home:help")])
        elif action == "url" and str(item.get("url") or "").startswith("http"):
            rows.append([InlineKeyboardButton(label, url=item["url"])])
    if not rows and bot:
        rows = [[InlineKeyboardButton("小程序", url=f"https://t.me/{bot}?startapp")]]
    return InlineKeyboardMarkup(rows)


def render_start(db, tenant, ident=None, *, bot: str = "", admin: bool = False) -> tuple[str, InlineKeyboardMarkup]:
    cfg = load_home(db)
    paid = tenant_usable(tenant)
    bot = _shown_bot(bot)
    uname = f"@{ident.username}" if ident and ident.username else "未同步用户名"
    name = (ident.display_name if ident else "") or ""
    until = fmt_until(tenant.paid_until) if tenant.paid_until else ("管理员" if paid else "未开通")
    title = (cfg.get("title") or "").strip() or f"{brand_name()} · {brand_title()}"
    body = cfg.get("body_paid") if paid else cfg.get("body_unpaid")
    status = f"当前状态  {'已开通至 ' + until if paid else '未开通'}"
    if paid:
        status += f"\n账号  {uname}"
    text = fill(
        f"{title}\n\n{body}\n\n{status}",
        bot=bot,
        until=until,
        username=uname,
        name=name,
    )
    kb = home_kb(cfg, bot=bot)
    if admin:
        rows = list(kb.inline_keyboard)
        rows.append([InlineKeyboardButton("管理员", callback_data="admin")])
        kb = InlineKeyboardMarkup(rows)
    return text, kb


def render_help(db, *, bot: str = "") -> str:
    cfg = load_home(db)
    return fill(cfg.get("help") or DEFAULT["help"], bot=bot)
