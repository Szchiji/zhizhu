from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.brand import brand_name, bot_username
from app.card_tpl import parse_mode_for, render as render_tpl
from app.models import Identity

BADGE = "🛡️"
PARSE_MODE = "HTML"


def _bot(name: str = "") -> str:
    return (bot_username() or name or "").lstrip("@")


def is_platform_bot(query: str, bot_name: str = "") -> bool:
    from app.brand import bot_aliases

    q = (query or "").strip().lstrip("@").split()[0].lower()
    if not q:
        return False
    names = bot_aliases()
    extra = (bot_name or "").lstrip("@").lower()
    if extra:
        names.add(extra)
    return q in names


def issuer_text(bot_username: str = "", db=None) -> str:
    return render_tpl("issuer", {"机器人": _bot(bot_username)}, db=db)


def issuer_kb(bot_username: str = "") -> InlineKeyboardMarkup:
    bot = _bot(bot_username)
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("再查一个", switch_inline_query_current_chat="")],
            [InlineKeyboardButton("开通平台登记", url=f"https://t.me/{bot}?startapp")],
        ]
    )


def card_text(ident: Identity, *, watermark: bool = False, bot_username: str = "", db=None) -> str:
    del watermark  # reserved
    extra = (ident.card_text or "").strip()
    until = "—"
    tenant = getattr(ident, "tenant", None)
    if tenant is not None:
        from app.services import fmt_until, is_staff, tenant_usable

        if getattr(tenant, "paid_until", None):
            until = fmt_until(tenant.paid_until) or "—"
        elif getattr(tenant, "status", "") == "owner" or is_staff(getattr(tenant, "owner_tg_id", 0)):
            until = "管理员"
        elif tenant_usable(tenant):
            until = "有效"
    return render_tpl(
        "paid",
        {
            "机器人": _bot(bot_username),
            "姓名": (ident.display_name or "未填姓名").strip(),
            "账号": f"@{ident.username}" if ident.username else "未绑定",
            "ID": ident.official_user_id or "—",
            "正文": extra,
            "有效期": until,
        },
        db=db,
    )


def promo_text(bot_name: str = "", name: str = "", db=None) -> str:
    if name and is_platform_bot(name, bot_name):
        return issuer_text(bot_name, db=db)
    query = f"@{name.lstrip('@')}" if name else ""
    return render_tpl(
        "unpaid",
        {
            "机器人": _bot(bot_name),
            "查询词": query or "该账号",
        },
        db=db,
    )


def card_kb(ident: Identity | None = None, *, share_url: str = "", bot_username: str = "", username: str = "") -> InlineKeyboardMarkup:
    bot = _bot(bot_username)
    uname = username or (ident.username if ident else "") or ""
    uname = uname.lstrip("@")
    if uname and is_platform_bot(uname, bot):
        return issuer_kb(bot)
    rows: list[list[InlineKeyboardButton]] = []
    if ident and uname:
        rows.append([InlineKeyboardButton("联系他", url=f"https://t.me/{uname}")])
    rows.append([InlineKeyboardButton("再查一个", switch_inline_query_current_chat="")])
    rows.append([InlineKeyboardButton("开通平台登记", url=f"https://t.me/{bot}?startapp")])
    return InlineKeyboardMarkup(rows)


async def send_card(message, ident: Identity, *, bot=None, bot_username: str = "", share: str = "", db=None) -> None:
    text = card_text(ident, bot_username=bot_username, db=db)
    kb = card_kb(ident, share_url=share, bot_username=bot_username)
    mode = parse_mode_for(db) or PARSE_MODE
    if bot and ident.official_user_id:
        try:
            photos = await bot.get_user_profile_photos(ident.official_user_id, limit=1)
            if photos.total_count:
                await message.reply_photo(
                    photos.photos[0][-1].file_id,
                    caption=text[:1024],
                    reply_markup=kb,
                    parse_mode=mode,
                )
                return
        except Exception:
            pass
    await message.reply_text(text, reply_markup=kb, parse_mode=mode)


def alert_text(ident: Identity) -> str:
    text = ident.alert_text or f"此为{brand_name()}平台登记身份"
    uid = ident.official_user_id or ""
    uname = f"@{ident.username}" if ident.username else ""
    return f"{text}\n{uname}  {uid}".strip()[:200]


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
    return "无法完成核验：对方尚未登记平台用户 ID，或转发来源已隐藏。"
