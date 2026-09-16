from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.models import Identity


def card_text(ident: Identity, *, watermark: bool = False, bot_username: str = "") -> str:
    name = ident.display_name or "—"
    uname = f"@{ident.username}" if ident.username else "—"
    uid = ident.official_user_id or "—"
    extra = (ident.card_text or "").strip()
    body = (
        "✅  官方登记\n"
        "━━━━━━━━━━━━\n"
        f"姓名    {name}\n"
        f"账号    {uname}\n"
        f"ID      {uid}\n"
        "━━━━━━━━━━━━"
    )
    if extra:
        body += f"\n{extra}"
    else:
        body += "\n仅以上登记为官方账号。"
    return body


async def send_card(message, ident: Identity, *, bot=None, bot_username: str = "", share: str = "") -> None:
    text = card_text(ident, bot_username=bot_username)
    kb = card_kb(ident, share_url=share, bot_username=bot_username)
    if bot and ident.official_user_id:
        try:
            photos = await bot.get_user_profile_photos(ident.official_user_id, limit=1)
            if photos.total_count:
                file_id = photos.photos[0][-1].file_id
                await message.reply_photo(file_id, caption=text[:1024], reply_markup=kb)
                return
        except Exception:
            pass
    await message.reply_text(text, reply_markup=kb)


def alert_text(ident: Identity) -> str:
    text = ident.alert_text or "此为官方登记账号"
    uid = ident.official_user_id or ""
    uname = f"@{ident.username}" if ident.username else ""
    return f"{text}\n{uname}  {uid}".strip()[:200]


def card_kb(ident: Identity, *, share_url: str = "", bot_username: str = "") -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    if ident.username:
        row.append(InlineKeyboardButton("联系此账号", url=f"https://t.me/{ident.username.lstrip('@')}"))
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
