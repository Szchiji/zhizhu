from __future__ import annotations

import os
import re

from app.config import BOT_USERNAME, BRAND_NAME, BRAND_TITLE, MENU_TEXT

_LEGACY = {"", "蜘蛛", "蜘蛛核验", "zhizhusp_bot", "官方核验"}
_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,32}$")

_state = {
    "name": "",
    "title": BRAND_TITLE,
    "username": "",
    "api_username": "",
    "aliases": set(),
    "menu": MENU_TEXT,
    "ready": False,
}


def _clean(name: str) -> str:
    text = (name or "").strip().lstrip("@")
    if not text or text.lower() in {n.lower() for n in _LEGACY}:
        return ""
    return text if _NAME_RE.fullmatch(text) else text[:32]


def _split_aliases(raw: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for part in re.split(r"[,\s]+", raw or ""):
        name = _clean(part)
        key = name.lower()
        if name and key not in seen:
            seen.add(key)
            out.append(name)
    return out


def _rebuild(display: str = "", extra: str = "") -> None:
    api = _clean(_state.get("api_username") or "")
    env_display = _clean(os.getenv("BOT_DISPLAY") or os.getenv("BOT_USERNAME") or BOT_USERNAME)
    shown = _clean(display) or env_display or api
    names = _split_aliases(",".join([
        shown,
        api,
        extra,
        os.getenv("BOT_ALIASES") or "",
        BOT_USERNAME,
    ]))
    _state["username"] = shown
    _state["aliases"] = set(names)


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
    return (_state["username"] or _state["api_username"] or "").lstrip("@")


def bot_aliases() -> set[str]:
    names = {n.lstrip("@").lower() for n in _state["aliases"] if n}
    for extra in (bot_username(), _state.get("api_username") or ""):
        extra = extra.lstrip("@").lower()
        if extra:
            names.add(extra)
    return names


def menu_text() -> str:
    return _state["menu"] or "小程序"


def load_brand_settings(db=None) -> None:
    display = ""
    extra = ""
    if db is not None:
        from app.services import get_setting
        display = get_setting(db, "bot_display", "")
        extra = get_setting(db, "bot_aliases", "")
    _rebuild(display, extra)


def apply_bot_names(display: str, aliases: str = "") -> None:
    _rebuild(display, aliases)


async def refresh_from_bot(bot) -> None:
    try:
        me = await bot.get_me()
    except Exception:
        me = None
    if me and me.username:
        _state["api_username"] = me.username.lstrip("@")
    env_name = (os.getenv("BRAND_NAME") or "").strip()
    if env_name and env_name not in _LEGACY:
        _state["name"] = env_name
    elif me and me.first_name:
        _state["name"] = me.first_name.strip()
    try:
        from app.db import get_session
        db = get_session()
        try:
            load_brand_settings(db)
        finally:
            db.close()
    except Exception:
        _rebuild()
    _state["ready"] = True
