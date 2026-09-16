from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import BOT_USERNAME, BRAND_NAME
from app.models import Identity


def _bot(name: str = "") -> str:
    return (name or BOT_USERNAME or "zhizhusp_bot").lstrip("@")


def card_text(ident: Identity, *, watermark: bool = False, bot_username: str = "") -> str:
    bot = _bot(bot_username)
    name = ident.display_name or "—"
    uname = f"@{ident.username}" if ident.username else "—"
    uid = ident.official_user_id or "—"
    extra = (ident.card_text or "").strip()
    body = (
        f"✅  {BRAND_NAME}官方核验\n"
        f"来源  @{bot}\n"
        "━━━━━━━━━━━━\n"
        f"姓名    {name}\n"
        f"账号    {uname}\n"
        f"ID      {uid}\n"
        "━━━━━━━━━━━━\n"
    )
    if extra:
        body += extra + "\n\n"
    body += (
        "以上为官方登记，请谨防仿冒。\n"
        f"查其他人：输入 @{bot} 加空格再加用户名"
    )
    return body


def promo_text(bot_username: str = "", name: str = "") -> str:
    bot = _bot(bot_username)
    if name:
        return (
            f"@{name} 暂无官方登记\n\n"
            f"{BRAND_NAME}提供账号核验，避免被仿冒。\n"
            f"开通后可生成带 @{bot} 来源标识的官方卡。"
        )
    return (
        f"{BRAND_NAME} · 官方身份核验\n\n"
        "在输入框输入要查的 @用户名，即可出官方登记卡。\n"
        "开通后自己的账号也可生成同样的认证卡。"
    )


async def send_card(message, ident: Identity, *, bot=None, bot_username: str = "", share: str = "") -> None:
    text = card_text(ident, bot_username=bot_username)
    kb = card_kb(ident, share_url=share, bot_username=bot_username)
    if bot and ident.official_user_id:
        try:
            photos = await bot.get_user_profile_photos(ident.official_user_id, limit=1)
            if photos.total_count:
                await message.reply_photo(photos.photos[0][-1].file_id, caption=text[:1024], reply_markup=kb)
                return
        except Exception:
            pass
    await message.reply_text(text, reply_markup=kb)


def alert_text(ident: Identity) -> str:
    text = ident.alert_text or f"此为{BRAND_NAME}官方登记账号"
    uid = ident.official_user_id or ""
    uname = f"@{ident.username}" if ident.username else ""
    return f"{text}\n{uname}  {uid}".strip()[:200]


def card_kb(ident: Identity, *, share_url: str = "", bot_username: str = "") -> InlineKeyboardMarkup:
    bot = _bot(bot_username)
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    if ident.username:
        row.append(InlineKeyboardButton("联系登记账号", url=f"https://t.me/{ident.username.lstrip('@')}"))
    row.append(InlineKeyboardButton("继续查询", switch_inline_query_current_chat=""))
    rows.append(row)
    rows.append([InlineKeyboardButton("开通官方核验", url=f"https://t.me/{bot}?start=pay")])
    return InlineKeyboardMarkup(rows)


def share_url(bot_username: str, tenant_id: int) -> str:
    bot = _bot(bot_username)
    if not bot:
        return ""
    return f"https://t.me/{bot}?start=v{tenant_id}"


def extract_forward(msg):
    src_id = None
    src_name = "未知"
    if getattr(msg, "forward_from", None):
        return msg.forward_from.id, msg.forward_from.full_name
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
