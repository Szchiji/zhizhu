from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.brand import brand_name, bot_username
from app.models import Identity


def _bot(name: str = "") -> str:
    return (name or bot_username()).lstrip("@")


def _row(label: str, value: str) -> str:
    return f"{label}    {value}"


def card_text(ident: Identity, *, watermark: bool = False, bot_username: str = "") -> str:
    bot = _bot(bot_username)
    name = (ident.display_name or "未填姓名").strip()
    uname = f"@{ident.username}" if ident.username else "未绑定"
    uid = str(ident.official_user_id or "—")
    extra = (ident.card_text or "").strip()
    brand = brand_name()
    lines = [
        f"✅  {brand}官方认证",
        "",
        _row("姓名", name),
        _row("账号", uname),
        _row("ID  ", uid),
    ]
    if extra:
        lines += ["", extra]
    lines += [
        "",
        "────────────",
        _row("出具", f"@{bot}"),
        _row("复查", f"@{bot} + 用户名"),
        _row("开通", "点下方按钮"),
    ]
    return "\n".join(lines)


def promo_text(bot_name: str = "", name: str = "") -> str:
    bot = _bot(bot_name)
    brand = brand_name()
    if name:
        return "\n".join([
            f"@{name}  尚未登记",
            "",
            f"{brand} 官方核验",
            _row("查询", f"@{bot} + 用户名"),
            _row("开通", "点下方按钮"),
            "",
            "开通后自动出官方认证卡，防仿冒。",
        ])
    return "\n".join([
        f"{brand} · 官方身份核验",
        "",
        _row("查询", f"@{bot} + 用户名"),
        _row("开通", "点下方按钮"),
    ])


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
    text = ident.alert_text or f"此为{brand_name()}官方登记账号"
    uid = ident.official_user_id or ""
    uname = f"@{ident.username}" if ident.username else ""
    return f"{text}\n{uname}  {uid}".strip()[:200]


def card_kb(ident: Identity, *, share_url: str = "", bot_username: str = "") -> InlineKeyboardMarkup:
    bot = _bot(bot_username)
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    if ident.username:
        row.append(InlineKeyboardButton("联系他", url=f"https://t.me/{ident.username.lstrip('@')}"))
    row.append(InlineKeyboardButton("再查一个", switch_inline_query_current_chat=""))
    rows.append(row)
    rows.append([InlineKeyboardButton("我也要官方认证", url=f"https://t.me/{bot}?start=pay")])
    return InlineKeyboardMarkup(rows)


def share_url(bot_name: str, tenant_id: int) -> str:
    bot = _bot(bot_name)
    if not bot:
        return ""
    return f"https://t.me/{bot}?start=v{tenant_id}"


def extract_forward(msg):
    if getattr(msg, "forward_from", None):
        return msg.forward_from.id, msg.forward_from.full_name
    origin = getattr(msg, "forward_origin", None)
    if origin is not None:
        user = getattr(origin, "sender_user", None)
        if user:
            return user.id, user.full_name
    return None, "未知"


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
