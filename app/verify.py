from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.models import Identity


def card_text(ident: Identity, *, watermark: bool = True, bot_username: str = "") -> str:
    name = ident.display_name or "未设置"
    uname = f"@{ident.username}" if ident.username else "无用户名"
    uid = ident.official_user_id or "未设置"
    extra = ""
    if watermark:
        if bot_username:
            extra = f"\n\n核验请用 @{bot_username}，点链接或转发可疑私聊。"
        else:
            extra = "\n\nPowered by 核验平台"
    return (
        f"官方身份\n"
        f"{name}（{uname}）\n"
        f"User ID：{uid}\n"
        f"只认这一个号，其他同名都不是本人。"
        f"{extra}"
    )


def alert_text(ident: Identity) -> str:
    text = ident.alert_text or "这是公示的官方账号，只认这一个号"
    uid = ident.official_user_id or ""
    uname = f"@{ident.username}" if ident.username else ""
    return f"{text}\n{uname}\nID {uid}".strip()[:200]


def card_kb(ident: Identity, *, share_url: str = "", bot_username: str = "") -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    rows.append([InlineKeyboardButton("确认是本人", callback_data="info")])
    row: list[InlineKeyboardButton] = []
    if ident.username:
        row.append(InlineKeyboardButton("私聊正主", url=f"https://t.me/{ident.username.lstrip('@')}"))
    elif ident.official_user_id:
        row.append(InlineKeyboardButton("打开资料", url=f"tg://user?id={ident.official_user_id}"))
    if share_url:
        row.append(InlineKeyboardButton("打开核验", url=share_url))
    if row:
        rows.append(row)
    if bot_username:
        rows.append([InlineKeyboardButton("发给朋友核验", switch_inline_query="")])
    return InlineKeyboardMarkup(rows)


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
        return f"核验结果：是本人\n来源：{src_name}\nID：{src_id}"
    if official and src_id:
        return (
            f"核验结果：不是本人\n"
            f"来源：{src_name}\n来源 ID：{src_id}\n官方 ID：{official}\n"
            f"请不要转账，先打电话确认。"
        )
    return "无法判断。对方需先在本机器人点「我的官方身份」登记 User ID。\n若对方关闭了转发来源，也核验不了。"
