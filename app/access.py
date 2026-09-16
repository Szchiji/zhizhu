from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import ADMIN_TG_IDS
from app.db import get_session
from app.services import get_or_create_tenant, get_setting, is_staff

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


def force_channel(db) -> str:
    return (get_setting(db, "force_channel", "") or "").strip()


def channel_link(channel: str) -> str:
    raw = (channel or "").strip()
    if raw.startswith("http"):
        return raw
    name = raw.lstrip("@")
    if name.startswith("-100"):
        return f"https://t.me/c/{name[4:]}"
    return f"https://t.me/{name}"


async def joined_channel(user_id: int, channel: str) -> bool:
    if not channel or not _bot:
        return True
    chat = channel if channel.startswith("@") or channel.startswith("-") else f"@{channel.lstrip('@')}"
    if chat.startswith("http"):
        return True
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
        channel = force_channel(db)
    finally:
        db.close()
    if channel and not await joined_channel(user_id, channel):
        return f"请先订阅频道 {channel} 后再使用。", channel_link(channel)
    return None, ""


def subscribe_kb(url: str) -> InlineKeyboardMarkup | None:
    if not url:
        return None
    return InlineKeyboardMarkup([[InlineKeyboardButton("加入频道", url=url)]])
