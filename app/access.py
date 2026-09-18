from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import ADMIN_TG_IDS
from app.db import get_session
from app.services import get_or_create_tenant, get_setting, is_staff, set_setting

_bot = None


def set_bot(bot) -> None:
    global _bot
    _bot = bot


def is_blocked(tenant) -> bool:
    if not tenant:
        return False
    if is_staff(tenant.owner_tg_id):
        return False
    return tenant.status == "suspended"


def force_on(db) -> bool:
    return get_setting(db, "force_channel_on", "0") == "1"


def force_channel(db) -> str:
    return (get_setting(db, "force_channel", "") or "").strip()


def normalize_channel(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    if text.startswith("https://t.me/+") or text.startswith("t.me/+"):
        return text if text.startswith("http") else "https://" + text
    if text.startswith("https://t.me/") or text.startswith("t.me/"):
        part = text.split("t.me/", 1)[1].split("?")[0].strip("/")
        if part.startswith("+"):
            return text if text.startswith("http") else "https://" + text
        if part.startswith("c/"):
            num = part[2:].split("/")[0]
            return f"-100{num}" if not num.startswith("100") else f"-{num}"
        return "@" + part.lstrip("@")
    if text.startswith("+"):
        return "https://t.me/" + text
    if text.startswith("@"):
        return text
    digits = text.lstrip("-")
    if digits.isdigit():
        if text.startswith("-"):
            return text
        if text.startswith("100"):
            return "-" + text
        return "-100" + text
    return "@" + text.lstrip("@")


def channel_chat_id(channel: str):
    raw = normalize_channel(channel)
    if raw.startswith("http"):
        return raw
    if raw.lstrip("-").isdigit():
        try:
            return int(raw)
        except ValueError:
            return raw
    return raw


def channel_link(channel: str) -> str:
    raw = normalize_channel(channel)
    if raw.startswith("http"):
        return raw
    if raw.startswith("-100") and raw[1:].isdigit():
        return f"https://t.me/c/{raw[4:]}/1"
    if raw.startswith("-"):
        return ""
    return f"https://t.me/{raw.lstrip('@')}"


async def describe_channel(channel: str) -> tuple[str, str]:
    raw = normalize_channel(channel)
    title = ""
    url = channel_link(raw)
    chat_ref = channel_chat_id(raw)
    if raw.startswith("http") and "/" in raw and raw.split("t.me/")[-1].startswith("+"):
        url = raw
    if _bot and not (isinstance(chat_ref, str) and chat_ref.startswith("http")):
        try:
            chat = await _bot.get_chat(chat_ref)
            title = (getattr(chat, "title", None) or getattr(chat, "full_name", None) or "").strip()
            uname = getattr(chat, "username", None)
            if uname:
                url = f"https://t.me/{uname.lstrip('@')}"
                if not title:
                    title = f"@{uname.lstrip('@')}"
            else:
                invite = getattr(chat, "invite_link", None) or ""
                if not invite:
                    try:
                        invite = await _bot.export_chat_invite_link(chat.id)
                    except Exception:
                        invite = ""
                if invite:
                    url = invite
        except Exception:
            pass
    if not title:
        if raw.startswith("@"):
            title = raw
        else:
            title = "指定频道"
    return title, url


async def joined_channel(user_id: int, channel: str) -> bool:
    if not channel or not _bot:
        return True
    chat = channel_chat_id(channel)
    if isinstance(chat, str) and chat.startswith("http"):
        db = get_session()
        try:
            stored = get_setting(db, "force_channel_chat", "") or get_setting(db, "force_channel", channel)
        finally:
            db.close()
        chat = channel_chat_id(stored) if stored else chat
        if isinstance(chat, str) and chat.startswith("http"):
            return False
    try:
        member = await _bot.get_chat_member(chat, user_id)
        return member.status in {"creator", "administrator", "member", "restricted"}
    except Exception:
        return False


async def gate_user(user_id: int) -> tuple[str | None, str]:
    if not user_id:
        return "未登录", ""
    if user_id in ADMIN_TG_IDS:
        return None, ""
    db = get_session()
    try:
        tenant = get_or_create_tenant(db, user_id)
        if is_blocked(tenant):
            return "账号已被停用，无法使用本机器人。", ""
        on = force_on(db)
        channel = force_channel(db)
    finally:
        db.close()
    if not (on and channel):
        return None, ""
    if await joined_channel(user_id, channel):
        return None, ""
    title, url = await describe_channel(channel)
    db = get_session()
    try:
        if title:
            set_setting(db, "force_channel_title", title)
        if url:
            set_setting(db, "force_channel_url", url)
    finally:
        db.close()
    return f"请先订阅频道「{title or '指定频道'}」后再使用。", url or channel_link(channel)


def subscribe_kb(url: str) -> InlineKeyboardMarkup | None:
    if not url or not str(url).startswith("http"):
        return None
    return InlineKeyboardMarkup([[InlineKeyboardButton("加入频道", url=url)]])
