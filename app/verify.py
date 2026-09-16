from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.models import Identity


def card_text(ident: Identity, *, watermark: bool = False, bot_username: str = "") -> str:
    if ident.card_text:
        return ident.card_text
    name = ident.display_name or "—"
    uname = f"@{ident.username}" if ident.username else "—"
    uid = ident.official_user_id or "—"
    return (
        "官方身份核验\n\n"
        f"姓名    {name}\n"
        f"账号    {uname}\n"
        f"ID      {uid}\n\n"
        "仅以上登记为官方账号，其他同名带号均非本人。"
    )


def alert_text(ident: Identity) -> str:
    text = ident.alert_text or "此为官方登记账号"
    uid = ident.official_user_id or ""
    uname = f"@{ident.username}" if ident.username else ""
    return f"{text}\n{uname}  {uid}".strip()[:200]


def card_kb(ident: Identity, *, share_url: str = "", bot_username: str = "") -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    if ident.username:
        row.append(InlineKeyboardButton("联系登记账号", url=f"https://t.me/{ident.username.lstrip('@')}"))
    elif ident.official_user_id:
        row.append(InlineKeyboardButton("查看资料", url=f"tg://user?id={ident.official_user_id}"))
    if share_url:
        row.append(InlineKeyboardButton("再次查询", url=share_url))
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows) if rows else InlineKeyboardMarkup([])


def share_url(bot_username: str, tenant_id: int) -> str:
    if not bot_username:
        return ""
    return f"https://t.me/{bot_username.lstrip('@')}?start=v{tenant_id}"


def extract_forward(msg):
    src_id = None
    src_name = "未知"
    if getattr(msg, "forward_from", None):
        src_id = msg.forward_from.id
        src_name = msg.forward_from.full_name
        return src_id, src_name
    origin = getattr(msg, "forward_origin", None)
    if origin is not None:
        user = getattr(origin, "sender_user", None)
        if user:
            src_id = user.id
            src_name = user.full_name
    return src_id, src_name


def is_forwarded(msg) -> bool:
    if not msg:
        return False
    return bool(
        getattr(msg, "forward_origin", None)
        or getattr(msg, "forward_from", None)
        or getattr(msg, "forward_from_user", None)
        or getattr(msg, "forward_date", None)
    )


def judge(ident: Identity, src_id: int | None, src_name: str) -> str:
    official = ident.official_user_id
    if official and src_id == official:
        return f"核验结果：与登记一致\n来源：{src_name}\nID：{src_id}"
    if official and src_id:
        return (
            f"核验结果：与登记不符\n"
            f"来源：{src_name}\n来源 ID：{src_id}\n登记 ID：{official}"
        )
    return "无法完成核验：对方尚未登记官方 ID，或转发来源已隐藏。"
