from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.access import get_bot
from app.brand import bot_username
from app.config import ADMIN_TG_IDS
from app.db import get_session
from app.models import utcnow
from app.services import find_paid_by_tg_id, get_or_create_tenant, get_setting, set_setting, tenant_usable
from app.tg_webapp import require_webapp_user
from app.verify import PARSE_MODE, card_kb, card_text

_SRC_OK = {"found", "empty", "invite"}
_STARTAPP_RE = re.compile(
    r"^ref_([A-Za-z0-9]+)(?:_src_([A-Za-z0-9]+))?$",
    re.IGNORECASE,
)
_LEGACY_RE = re.compile(r"^ref(\d+)$", re.IGNORECASE)
_ALPH = "0123456789abcdefghijklmnopqrstuvwxyz"


def ref_on(db: Session) -> bool:
    return get_setting(db, "ref_on", "1") != "0"


def ref_days(db: Session) -> int:
    try:
        return max(1, min(365, int(get_setting(db, "ref_days", "7") or 7)))
    except ValueError:
        return 7


def ref_cycle(db: Session) -> int:
    try:
        return max(1, min(50, int(get_setting(db, "ref_cycle", "3") or 3)))
    except ValueError:
        return 3


def ref_bind_hours(db: Session) -> int:
    try:
        return max(1, min(720, int(get_setting(db, "ref_bind_hours", "24") or 24)))
    except ValueError:
        return 24


def encode_ref_code(tg_id: int) -> str:
    n = abs(int(tg_id))
    if n == 0:
        return "0"
    out: list[str] = []
    while n:
        n, r = divmod(n, 36)
        out.append(_ALPH[r])
    return "".join(reversed(out))


def decode_ref_code(code: str) -> int | None:
    raw = (code or "").strip().lower()
    if not raw or not re.fullmatch(r"[0-9a-z]+", raw):
        return None
    try:
        return int(raw, 36)
    except ValueError:
        return None


def parse_ref_payload(payload: str) -> tuple[int | None, str]:
    """Return (inviter_tg_id, src). src defaults to invite."""
    raw = (payload or "").strip()
    if not raw:
        return None, ""
    # strip common wrappers
    if "startapp=" in raw.lower():
        raw = re.split(r"startapp=", raw, flags=re.I)[-1]
    raw = raw.split("&")[0].split("#")[0].strip()
    m = _STARTAPP_RE.match(raw)
    if m:
        inviter = decode_ref_code(m.group(1))
        src = (m.group(2) or "invite").lower()
        if src not in _SRC_OK:
            src = "invite"
        return inviter, src
    m2 = _LEGACY_RE.match(raw)
    if m2:
        return int(m2.group(1)), "invite"
    # bare digits after ref (legacy ref123 with noise)
    if raw.lower().startswith("ref"):
        digits = "".join(ch for ch in raw[3:] if ch.isdigit())
        if digits:
            return int(digits), "invite"
    return None, ""


def build_startapp(tg_id: int, src: str = "invite") -> str:
    src_n = (src or "invite").lower()
    if src_n not in _SRC_OK:
        src_n = "invite"
    return f"ref_{encode_ref_code(int(tg_id))}_src_{src_n}"


def invite_link(tg_id: int, *, src: str = "invite") -> str:
    bot = (bot_username() or "").lstrip("@")
    if not bot:
        return ""
    return f"https://t.me/{bot}/app?startapp={build_startapp(tg_id, src)}"


def _parse_bind(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    if text.isdigit():
        return {"inviter": int(text), "src": "invite", "ts": ""}
    try:
        data = json.loads(text)
        if isinstance(data, dict) and data.get("inviter") is not None:
            return {
                "inviter": int(data["inviter"]),
                "src": str(data.get("src") or "invite"),
                "ts": str(data.get("ts") or ""),
            }
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return None


def _bind_fresh(db: Session, bind: dict[str, Any]) -> bool:
    ts = bind.get("ts") or ""
    if not ts:
        return True  # legacy binds without ts remain valid
    try:
        when = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
    except ValueError:
        return True
    hours = ref_bind_hours(db)
    return utcnow() - when.replace(tzinfo=None) <= timedelta(hours=hours)


def get_bind(db: Session, invitee_tg: int) -> dict[str, Any] | None:
    return _parse_bind(get_setting(db, f"invitee:{int(invitee_tg)}"))


def bind_referrer(db: Session, *, invitee_tg: int, payload: str, src: str = "") -> dict[str, Any]:
    """First-open bind. Does not overwrite. Self-ref invalid. Returns status dict."""
    inviter, parsed_src = parse_ref_payload(payload)
    if src and src.lower() in _SRC_OK:
        parsed_src = src.lower()
    if not inviter:
        return {"ok": False, "reason": "invalid"}
    if int(inviter) == int(invitee_tg):
        return {"ok": False, "reason": "self"}
    key = f"invitee:{int(invitee_tg)}"
    existing = get_setting(db, key)
    if existing:
        bind = _parse_bind(existing) or {}
        return {
            "ok": True,
            "bound": True,
            "kept": True,
            "inviter": bind.get("inviter"),
            "src": bind.get("src") or parsed_src or "invite",
        }
    blob = json.dumps(
        {
            "inviter": int(inviter),
            "src": parsed_src or "invite",
            "ts": utcnow().isoformat(timespec="seconds"),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    set_setting(db, key, blob)
    _append_recent(
        db,
        inviter_tg=int(inviter),
        invitee_tg=int(invitee_tg),
        src=parsed_src or "invite",
        status="opened",
    )
    return {
        "ok": True,
        "bound": True,
        "kept": False,
        "inviter": int(inviter),
        "src": parsed_src or "invite",
    }


def _paid_count(db: Session, inviter_tg: int) -> int:
    try:
        return max(0, int(get_setting(db, f"ref_paid:{int(inviter_tg)}", "0") or 0))
    except ValueError:
        return 0


def _reward_total(db: Session, inviter_tg: int) -> int:
    try:
        return max(0, int(get_setting(db, f"ref_reward_total:{int(inviter_tg)}", "0") or 0))
    except ValueError:
        return 0


def _extend_days(tenant, days: int) -> None:
    if not tenant or days <= 0:
        return
    base = utcnow()
    if tenant.paid_until and tenant.paid_until > base:
        base = tenant.paid_until
    tenant.paid_until = base + timedelta(days=int(days))
    if tenant.status not in {"owner", "suspended"}:
        tenant.status = "active"


def _append_recent(
    db: Session,
    *,
    inviter_tg: int,
    invitee_tg: int,
    src: str,
    status: str,
    name: str = "",
) -> None:
    key = f"ref_recent:{int(inviter_tg)}"
    try:
        items = json.loads(get_setting(db, key, "[]") or "[]")
        if not isinstance(items, list):
            items = []
    except json.JSONDecodeError:
        items = []
    # update existing by invitee
    updated = False
    for it in items:
        if int(it.get("tg") or 0) == int(invitee_tg):
            it["status"] = status
            it["src"] = src or it.get("src") or "invite"
            it["ts"] = utcnow().isoformat(timespec="seconds")
            if name:
                it["name"] = name
            updated = True
            break
    if not updated:
        items.insert(
            0,
            {
                "tg": int(invitee_tg),
                "name": name or str(invitee_tg),
                "src": src or "invite",
                "status": status,
                "ts": utcnow().isoformat(timespec="seconds"),
            },
        )
    set_setting(db, key, json.dumps(items[:30], ensure_ascii=False, separators=(",", ":")), commit=False)


def _src_label(src: str) -> str:
    return {"found": "分享查询卡", "empty": "空态卡", "invite": "邀请链接"}.get(src or "", "邀请链接")


def progress_payload(db: Session, tg_id: int) -> dict[str, Any]:
    cycle = ref_cycle(db)
    days = ref_days(db)
    paid = _paid_count(db, tg_id)
    cycle_progress = paid % cycle
    # After a completed cycle, progress resets to 0 for the next round.
    shown = cycle_progress
    need = cycle - shown if shown else cycle
    try:
        recent_raw = json.loads(get_setting(db, f"ref_recent:{int(tg_id)}", "[]") or "[]")
        if not isinstance(recent_raw, list):
            recent_raw = []
    except json.JSONDecodeError:
        recent_raw = []
    recent = []
    for it in recent_raw[:15]:
        st = it.get("status") or "opened"
        label = {"paid": "已开通 · 计入", "opened": "已点开 · 未开通"}.get(st, st)
        recent.append(
            {
                "name": it.get("name") or str(it.get("tg") or ""),
                "tg": it.get("tg"),
                "src": it.get("src") or "invite",
                "src_label": _src_label(str(it.get("src") or "invite")),
                "status": st,
                "status_label": label,
                "ts": it.get("ts") or "",
            }
        )
    code = encode_ref_code(int(tg_id))
    link = invite_link(tg_id, src="invite")
    return {
        "ok": True,
        "on": ref_on(db),
        "days": days,
        "reward_days": days,
        "cycle_target": cycle,
        "cycle_progress": shown,
        "invited_paid": paid,
        "need_more": need,
        "total_reward_days": _reward_total(db, tg_id),
        "ref_code": code,
        "link": link,
        "invite_link": link,
        "bind_hours": ref_bind_hours(db),
        "recent": recent,
        "title": (
            f"已邀 {shown} / 再邀 {need} 人得 +{days} 天"
            if need
            else f"已邀 {shown} / 再邀 {cycle} 人得 +{days} 天"
        ),
    }


def grant_referral(db: Session, tenant) -> int:
    """After successful payment: count invite once; every cycle grant inviter days; invitee bonus once.

    Returns days granted to the *inviter* this call (0 if none).
    """
    if tenant is None or not ref_on(db):
        return 0
    invitee_tg = int(tenant.owner_tg_id)
    counted_key = f"ref_counted:{invitee_tg}"
    if get_setting(db, counted_key):
        return 0
    # legacy one-shot key
    rewarded_key = f"ref_rewarded:{tenant.id}"
    if get_setting(db, rewarded_key):
        return 0

    bind = get_bind(db, invitee_tg)
    if not bind:
        return 0
    if not _bind_fresh(db, bind):
        return 0
    try:
        inviter_tg = int(bind["inviter"])
    except (KeyError, TypeError, ValueError):
        return 0
    if inviter_tg == invitee_tg:
        return 0

    days = ref_days(db)
    cycle = ref_cycle(db)
    inviter = get_or_create_tenant(db, inviter_tg)
    if inviter.status == "suspended":
        return 0

    # invitee gift once
    invitee_bonus_key = f"ref_invitee_bonus:{tenant.id}"
    if not get_setting(db, invitee_bonus_key):
        _extend_days(tenant, days)
        set_setting(db, invitee_bonus_key, "1", commit=False)

    # mark counted once per tg id
    set_setting(db, counted_key, str(inviter_tg), commit=False)
    set_setting(db, rewarded_key, "1", commit=False)

    new_count = _paid_count(db, inviter_tg) + 1
    set_setting(db, f"ref_paid:{inviter_tg}", str(new_count), commit=False)

    name = ""
    try:
        ident = getattr(tenant, "identity", None)
        if ident and getattr(ident, "display_name", None):
            name = str(ident.display_name)
        elif ident and getattr(ident, "username", None):
            name = "@" + str(ident.username).lstrip("@")
    except Exception:
        name = ""
    _append_recent(
        db,
        inviter_tg=inviter_tg,
        invitee_tg=invitee_tg,
        src=str(bind.get("src") or "invite"),
        status="paid",
        name=name or str(invitee_tg),
    )

    granted = 0
    if new_count > 0 and new_count % cycle == 0:
        _extend_days(inviter, days)
        granted = days
        total = _reward_total(db, inviter_tg) + days
        set_setting(db, f"ref_reward_total:{inviter_tg}", str(total), commit=False)

    db.commit()
    return granted


def referral_banner(db: Session, invitee_tg: int) -> dict[str, Any] | None:
    """Landing gift banner when valid ref present and user not yet paid."""
    tenant = get_or_create_tenant(db, invitee_tg)
    if tenant_usable(tenant):
        return None
    bind = get_bind(db, invitee_tg)
    if not bind or not _bind_fresh(db, bind):
        return None
    inviter_tg = int(bind["inviter"])
    if inviter_tg == int(invitee_tg):
        return None
    days = ref_days(db)
    inviter = get_or_create_tenant(db, inviter_tg)
    uname = ""
    try:
        ident = getattr(inviter, "identity", None)
        if ident and getattr(ident, "username", None):
            uname = "@" + str(ident.username).lstrip("@")
        elif ident and getattr(ident, "display_name", None):
            uname = str(ident.display_name)
    except Exception:
        uname = ""
    if not uname:
        uname = f"好友{encode_ref_code(inviter_tg)}"
    return {
        "show": True,
        "days": days,
        "inviter_name": uname,
        "ref_code": encode_ref_code(inviter_tg),
        "src": bind.get("src") or "invite",
        "bind_hours": ref_bind_hours(db),
        "title": f"好友送你 {days} 天体验",
        "subtitle": f"来自 {uname} 的邀请 · 开通任意套餐额外 +{days} 天",
    }


def remount_referral(app) -> None:
    @app.get("/api/mini/referral")
    async def my_referral(user_id: int = 0, init_data: str = ""):
        uid = require_webapp_user(init_data=init_data, body={"user_id": user_id})
        if not uid:
            return JSONResponse({"error": "未登录"}, status_code=401)
        db = get_session()
        try:
            data = progress_payload(db, uid)
            banner = referral_banner(db, uid)
            data["banner"] = banner
            return data
        finally:
            db.close()

    @app.get("/api/mini/invite/progress")
    async def invite_progress(user_id: int = 0, init_data: str = ""):
        uid = require_webapp_user(init_data=init_data, body={"user_id": user_id})
        if not uid:
            return JSONResponse({"error": "未登录"}, status_code=401)
        db = get_session()
        try:
            return progress_payload(db, uid)
        finally:
            db.close()

    @app.post("/api/mini/ref/bind")
    async def mini_ref_bind(request: Request):
        body = await request.json()
        uid = require_webapp_user(init_data=str(body.get("init_data") or ""), body=body)
        if not uid:
            return JSONResponse({"error": "未登录"}, status_code=401)
        payload = str(body.get("start_param") or body.get("payload") or body.get("ref") or "").strip()
        src = str(body.get("src") or "").strip()
        if body.get("ref") and not str(body.get("start_param") or "").strip():
            code = str(body.get("ref")).strip()
            src_n = src or "invite"
            payload = f"ref_{code}_src_{src_n}" if not code.lower().startswith("ref") else code
        db = get_session()
        try:
            if not ref_on(db):
                return {"ok": False, "reason": "off"}
            result = bind_referrer(db, invitee_tg=uid, payload=payload, src=src)
            banner = referral_banner(db, uid)
            result["banner"] = banner
            result["days"] = ref_days(db)
            return result
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
            if body.get("cycle") not in (None, ""):
                set_setting(db, "ref_cycle", str(max(1, min(50, int(body.get("cycle"))))), commit=False)
            if body.get("bind_hours") not in (None, ""):
                set_setting(
                    db,
                    "ref_bind_hours",
                    str(max(1, min(720, int(body.get("bind_hours"))))),
                    commit=False,
                )
            db.commit()
            return {
                "ok": True,
                "on": ref_on(db),
                "days": ref_days(db),
                "cycle": ref_cycle(db),
                "bind_hours": ref_bind_hours(db),
            }
        finally:
            db.close()
