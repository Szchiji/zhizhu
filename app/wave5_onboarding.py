"""Wave5: profile onboarding banner + one-shot DM after first activation."""
from __future__ import annotations

import json
import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.services import get_setting, set_setting

log = logging.getLogger("zhizhu.wave5")


def profile_incomplete(ident) -> bool:
    if not ident:
        return True
    name = (getattr(ident, "display_name", None) or "").strip()
    uname = (getattr(ident, "username", None) or "").strip()
    return not name or not uname


def need_onboarding(tenant) -> bool:
    if not tenant:
        return False
    from app.services import tenant_usable

    if not tenant_usable(tenant):
        return False
    return profile_incomplete(getattr(tenant, "identity", None))


def dm_sent_key(tg_id: int) -> str:
    return f"onboard_dm:{int(tg_id)}"


def mark_dm_sent(db: Session, tg_id: int) -> None:
    set_setting(db, dm_sent_key(tg_id), "1", commit=False)


def was_dm_sent(db: Session, tg_id: int) -> bool:
    return get_setting(db, dm_sent_key(tg_id), "") == "1"


async def maybe_send_onboarding_dm(bot, db: Session, tenant) -> None:
    """Send one DM asking user to set display name / username in mini. Never raises."""
    if not bot or not tenant:
        return
    tg_id = int(getattr(tenant, "owner_tg_id", 0) or 0)
    if not tg_id or was_dm_sent(db, tg_id):
        return
    if not need_onboarding(tenant):
        return
    try:
        await bot.send_message(
            chat_id=tg_id,
            text=(
                "欢迎开通！请打开小程序「我的」，补全对外姓名与用户名，"
                "以便群内查询出卡。此消息只提醒一次。"
            ),
        )
        mark_dm_sent(db, tg_id)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        log.warning("onboarding dm failed tg=%s: %s", tg_id, exc)


def mount_wave5(app) -> None:
    @app.middleware("http")
    async def wave5_me_onboarding(request: Request, call_next):
        response = await call_next(request)
        if request.url.path != "/api/mini/me" or response.status_code != 200:
            return response
        try:
            body = b""
            async for chunk in response.body_iterator:
                body += chunk
            data = json.loads(body.decode() or "{}")
            if not isinstance(data, dict) or not data.get("ok"):
                return JSONResponse(data, status_code=response.status_code)
            need = False
            if data.get("paid"):
                dn = (data.get("display_name") or "").strip()
                un = (data.get("username") or "").strip()
                need = not dn or not un
            data["need_profile"] = need
            data["onboarding_banner"] = (
                "请先设置对外姓名与用户名，保存后即可用于查询出卡。" if need else ""
            )
            return JSONResponse(data, status_code=200)
        except Exception as exc:  # noqa: BLE001
            log.warning("wave5 me onboarding patch failed: %s", exc)
            return response
