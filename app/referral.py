from __future__ import annotations

from datetime import timedelta

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.access import get_bot
from app.brand import bot_username
from app.config import ADMIN_TG_IDS
from app.db import get_session
from app.models import utcnow
from app.services import find_paid_by_tg_id, get_or_create_tenant, get_setting, set_setting
from app.tg_webapp import require_webapp_user
from app.verify import PARSE_MODE, card_kb, card_text


def ref_on(db: Session) -> bool:
    return get_setting(db, "ref_on", "1") != "0"


def ref_days(db: Session) -> int:
    try:
        return max(1, min(365, int(get_setting(db, "ref_days", "7") or 7)))
    except ValueError:
        return 7


def bind_referrer(db: Session, *, invitee_tg: int, payload: str) -> None:
    raw = (payload or "").strip()
    if not raw.lower().startswith("ref"):
        return
    digits = "".join(ch for ch in raw[3:] if ch.isdigit())
    if not digits:
        return
    inviter_tg = int(digits)
    if inviter_tg == int(invitee_tg):
        return
    key = f"invitee:{int(invitee_tg)}"
    if get_setting(db, key):
        return
    set_setting(db, key, str(inviter_tg))


def grant_referral(db: Session, tenant) -> int:
    if tenant is None or not ref_on(db):
        return 0
    rewarded_key = f"ref_rewarded:{tenant.id}"
    if get_setting(db, rewarded_key):
        return 0
    raw = get_setting(db, f"invitee:{int(tenant.owner_tg_id)}")
    if not raw:
        return 0
    try:
        inviter_tg = int(raw)
    except ValueError:
        return 0
    if inviter_tg == int(tenant.owner_tg_id):
        return 0
    days = ref_days(db)
    inviter = get_or_create_tenant(db, inviter_tg)
    if inviter.status == "suspended":
        return 0
    base = utcnow()
    if inviter.paid_until and inviter.paid_until > base:
        base = inviter.paid_until
    inviter.paid_until = base + timedelta(days=days)
    if inviter.status not in {"owner", "suspended"}:
        inviter.status = "active"
    set_setting(db, rewarded_key, "1", commit=False)
    db.commit()
    return days


def invite_link(tg_id: int) -> str:
    bot = (bot_username() or "").lstrip("@")
    if not bot:
        return ""
    return f"https://t.me/{bot}?start=ref{int(tg_id)}"


def remount_referral(app) -> None:
    @app.get("/api/mini/referral")
    async def my_referral(user_id: int = 0, init_data: str = ""):
        uid = require_webapp_user(init_data=init_data, body={"user_id": user_id})
        if not uid:
            return JSONResponse({"error": "未登录"}, status_code=401)
        db = get_session()
        try:
            return {"ok": True, "on": ref_on(db), "days": ref_days(db), "link": invite_link(uid)}
        finally:
            db.close()

    @app.post("/api/mini/send-card")
    async def send_my_card(request: Request):
        body = await request.json()
        uid = require_webapp_user(init_data=str(body.get("init_data") or ""), body=body)
        if not uid:
            return JSONResponse({"error": "未登录"}, status_code=401)
        bot = get_bot()
        if bot is None:
            return JSONResponse({"error": "机器人未就绪"}, status_code=503)
        db = get_session()
        try:
            ident = find_paid_by_tg_id(db, uid)
            if not ident:
                return JSONResponse({"error": "尚未开通或资料未生效"}, status_code=400)
            await bot.send_message(
                chat_id=int(uid),
                text=card_text(ident, db=db),
                reply_markup=card_kb(ident),
                parse_mode=PARSE_MODE,
            )
            return {"ok": True}
        except Exception as exc:  # noqa: BLE001
            return JSONResponse({"error": f"发送失败: {exc}"}, status_code=400)
        finally:
            db.close()

    @app.post("/api/mini/admin/referral")
    async def admin_referral(request: Request):
        body = await request.json()
        uid = require_webapp_user(init_data=str(body.get("init_data") or ""), body=body)
        if uid not in ADMIN_TG_IDS:
            return JSONResponse({"error": "仅管理员"}, status_code=403)
        db = get_session()
        try:
            if "on" in body:
                set_setting(db, "ref_on", "1" if body.get("on") else "0", commit=False)
            if body.get("days") not in (None, ""):
                set_setting(db, "ref_days", str(max(1, min(365, int(body.get("days"))))), commit=False)
            db.commit()
            return {"ok": True, "on": ref_on(db), "days": ref_days(db)}
        finally:
            db.close()
