from __future__ import annotations

from app.config import BOT_USERNAME, BRAND_NAME, BRAND_TITLE, MENU_TEXT

_state = {
    "name": BRAND_NAME,
    "title": BRAND_TITLE,
    "username": BOT_USERNAME,
    "menu": MENU_TEXT,
    "ready": False,
}


def brand_name() -> str:
    return _state["name"] or BRAND_NAME or "蜘蛛"


def brand_title() -> str:
    return _state["title"] or BRAND_TITLE or "官方身份核验"


def bot_username() -> str:
    return (_state["username"] or BOT_USERNAME or "zhizhusp_bot").lstrip("@")


def menu_text() -> str:
    return _state["menu"] or MENU_TEXT or "开通套餐"


async def refresh_from_bot(bot) -> None:
    import os

    try:
        me = await bot.get_me()
    except Exception:
        return
    if me.username:
        _state["username"] = me.username.lstrip("@")
    if not os.getenv("BRAND_NAME") and me.first_name:
        _state["name"] = me.first_name
    if not os.getenv("BOT_USERNAME") and me.username:
        _state["username"] = me.username.lstrip("@")
    _state["ready"] = True
