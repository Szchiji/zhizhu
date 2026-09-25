"""Admin-configured Stars \u2194 USDT conversion rate (no live market FX)."""
from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from app.config import ADMIN_TG_IDS
from app.db import get_session
from app.services import add_admin_audit, get_setting, set_setting
from app.tg_webapp import require_webapp_user

# How many Telegram Stars equal 1 USDT. Admin-editable; not live market FX.
# Repo has no prior FX constant; STARS_MONTHLY*8 / USDT_YEARLY \u2248 40.4 \u2014 use 50 as a
# clear documented ballpark default (common Telegram Stars pricing chat estimate).
DEFAULT_STARS_PER_USDT = 50.0
SETTING_KEY = "stars_per_usdt"
MIN_RATE = 1.0
MAX_RATE = 10_000.0


def get_stars_per_usdt(db) -> float:
    raw = get_setting(db, SETTING_KEY, str(DEFAULT_STARS_PER_USDT))
    try:
        n = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_STARS_PER_USDT
    if n < MIN_RATE or n > MAX_RATE:
        return DEFAULT_STARS_PER_USDT
    return n


def set_stars_per_usdt(db, value: float | int | str) -> float:
    n = float(value)
    if n < MIN_RATE or n > MAX_RATE:
        raise ValueError(f"\u6c47\u7387\u987b\u5728 {MIN_RATE:g}\u2013{MAX_RATE:g} \u4e4b\u95f4\uff08Stars / 1 USDT\uff09")
    # Store compact; keep up to 4 decimals for fractional rates.
    stored = f"{n:.4f}".rstrip("0").rstrip(".")
    set_setting(db, SETTING_KEY, stored)
    return float(stored)


def stars_to_usdt(stars: float | int, rate: float) -> float:
    r = float(rate) or DEFAULT_STARS_PER_USDT
    return round(max(0.0, float(stars)) / r, 2)


def usdt_to_stars(usdt: float | int, rate: float) -> int:
    r = float(rate) or DEFAULT_STARS_PER_USDT
    return max(1, int(round(max(0.0, float(usdt)) * r)))


def _admin(body: dict | None = None, user_id: int = 0, init_data: str = "") -> int:
    del user_id
    uid = require_webapp_user(init_data=init_data, body=body)
    return uid if uid in ADMIN_TG_IDS else 0


def mount_fx_rate(app) -> None:
    @app.get("/api/mini/admin/fx_rate")
    async def get_fx(user_id: int = 0, init_data: str = ""):
        if not _admin(user_id=user_id, init_data=init_data):
            return JSONResponse({"error": "\u4ec5\u7ba1\u7406\u5458"}, status_code=403)
        db = get_session()
        try:
            rate = get_stars_per_usdt(db)
            return {
                "ok": True,
                "stars_per_usdt": rate,
                "default": DEFAULT_STARS_PER_USDT,
                "hint": f"1 USDT \u2248 {rate:g} Stars\uff08\u7ba1\u7406\u5458\u8bbe\u5b9a\uff0c\u975e\u5b9e\u65f6\u884c\u60c5\uff09",
            }
        finally:
            db.close()

    @app.post("/api/mini/admin/fx_rate")
    async def save_fx(request: Request):
        body = await request.json()
        admin = _admin(body=body)
        if not admin:
            return JSONResponse({"error": "\u4ec5\u7ba1\u7406\u5458"}, status_code=403)
        db = get_session()
        try:
            try:
                rate = set_stars_per_usdt(db, body.get("stars_per_usdt"))
            except (TypeError, ValueError) as exc:
                return JSONResponse({"error": str(exc)}, status_code=400)
            add_admin_audit(
                db,
                admin,
                "fx_rate",
                target_type="setting",
                target_id=SETTING_KEY,
                detail=f"stars_per_usdt={rate:g}",
            )
            db.commit()
            return {
                "ok": True,
                "stars_per_usdt": rate,
                "hint": f"1 USDT \u2248 {rate:g} Stars\uff08\u7ba1\u7406\u5458\u8bbe\u5b9a\uff0c\u975e\u5b9e\u65f6\u884c\u60c5\uff09",
            }
        finally:
            db.close()


def convert_payload(rate: float, *, stars: Any = None, usdt: Any = None) -> dict:
    """Helper for tests / optional convert endpoint."""
    out: dict[str, Any] = {"stars_per_usdt": rate}
    if stars is not None and str(stars).strip() != "":
        out["usdt"] = stars_to_usdt(float(stars), rate)
    if usdt is not None and str(usdt).strip() != "":
        out["stars"] = usdt_to_stars(float(usdt), rate)
    return out
