from __future__ import annotations

import os

from app.config import BOT_USERNAME, BRAND_NAME, BRAND_TITLE, MENU_TEXT

_LEGACY = {"", "蜘蛛", "蜘蛛核验", "zhizhusp_bot", "官方核验"}

_state = {
    "name": "",
    "title": BRAND_TITLE,
    "username": BOT_USERNAME if BOT_USERNAME not in _LEGACY else "",
    "menu": MENU_TEXT,
    "ready": False,
}


def brand_name() -> str:
    if _state["name"]:
        return _state["name"]
    env = (os.getenv("BRAND_NAME") or BRAND_NAME or "").strip()
    if env and env not in _LEGACY:
        return env
    return "官方核验"


def brand_title() -> str:
    return _state["title"] or "官方身份核验"


def bot_username() -> str:
    return (_state["username"] or "").lstrip("@")


def menu_text() -> str:
    return _state["menu"] or "小程序"


async def refresh_from_bot(bot) -> None:
    try:
        me = await bot.get_me()
    except Exception:
        return
    if me.username:
        _state["username"] = me.username.lstrip("@")
    env_name = (os.getenv("BRAND_NAME") or "").strip()
    if env_name and env_name not in _LEGACY:
        _state["name"] = env_name
    elif me.first_name:
        _state["name"] = me.first_name.strip()
    _state["ready"] = True
