from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import timedelta
from types import SimpleNamespace

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from telegram import Bot, MenuButtonWebApp, Update, WebAppInfo

from app.access import set_bot
from app.admin_api import mount_admin
from app.brand import refresh_from_bot
from app.config import (
    ADMIN_TG_IDS,
    PLATFORM_BOT_TOKEN,
    PUBLIC_BASE_URL,
    USDT_ADDRESS,
    USDT_CHAIN,
    USDT_CONFIRM_CODE_LIMIT,
    USDT_CONFIRM_CODE_WINDOW,
    USDT_CONFIRM_IP_LIMIT,
    USDT_CONFIRM_IP_WINDOW,
    USDT_CONFIRM_SECRET,
    WEBHOOK_BASE_URL,
    WEBHOOK_SECRET,
)
from app.crypto_token import decrypt_token
from app.db import get_session, init_db
from app.entry import deny_json
from app.models import Identity, Order, Tenant, utcnow
from app.plans import PLANS, plan_stars, plan_usdt
from app.platform_bot import build_platform_app
from app.rate_limit import SlidingWindowLimiter
from app.services import (
    activate_order,
    add_event,
    audit_order_event,
    fulfill_stars_order,
    fmt_until,
    get_or_create_tenant,
    get_setting,
    new_code,
    open_order,
    parse_username,
    resolve_paid_identity,
    save_paid_profile,
    tenant_usable,
    unique_usdt_amount,
)
from app.tenant_bot import handle_tenant_update
from app.tg_webapp import require_webapp_user, user_from_init
from app.usdt_watch import watch_loop
from app.verify import card_text, promo_text

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("zhizhu")
templates = Jinja2Templates(directory="app/templates")
platform_app = None
_usdt_confirm_limiter = SlidingWindowLimiter()


def _client_ip(request: Request) -> str:
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if forwarded:
        return forwarded[:64]
    if request.client and request.client.host:
        return request.client.host[:64]
    return "unknown"


def _uid(body: dict | None = None, user_id: int = 0, init_data: str = "") -> int:
    """Identity from verified Telegram WebApp init_data only (ignores bare user_id)."""
    del user_id  # never trust client-supplied user_id as proof of identity
    return require_webapp_user(init_data=init_data, body=body)


def _drop_open_orders(db, tenant_id: int) -> None:
    while True:
        order = open_order(db, tenant_id)
        if not order:
            return
        add_event(db, order, "canceled", "replaced_by_new_checkout")
        db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global platform_app
    init_db()
    watcher = None
    if not PLATFORM_BOT_TOKEN:
        log.warning("PLATFORM_BOT_TOKEN missing")
        yield
        return
    platform_app = build_platform_app(PLATFORM_BOT_TOKEN)
    set_bot(platform_app.bot)
    await platform_app.initialize()
    await platform_app.start()
    await refresh_from_bot(platform_app.bot)
    if WEBHOOK_BASE_URL:
        url = f"{WEBHOOK_BASE_URL}/wh/platform"
        await platform_app.bot.set_webhook(
            url=url,
            secret_token=WEBHOOK_SECRET,
            drop_pending_updates=False,
            allowed_updates=["message", "callback_query", "inline_query", "pre_checkout_query", "purchased_paid_media"],
        )
        log.info("platform webhook %s", url)
    mini = f"{(PUBLIC_BASE_URL or WEBHOOK_BASE_URL or '').rstrip('/')}/mini?v=4"
    if mini.startswith("https://"):
        try:
            await platform_app.bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(text="小程序", web_app=WebAppInfo(url=mini))
            )
        except Exception as exc:
            log.warning("menu button failed: %s", exc)
    watcher = asyncio.create_task(watch_loop(platform_app.bot))
    yield
    if watcher:
        watcher.cancel()
    if platform_app:
        await platform_app.stop()
        await platform_app.shutdown()


app = FastAPI(title="VerifyHub", lifespan=lifespan)
mount_admin(app)


def _check_secret(secret: str | None) -> None:
    if WEBHOOK_SECRET and secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="bad secret")


@app.get("/healthz")
async def healthz():
    return {"ok": True}


@app.get("/")
async def root():
    return {"name": "verifyhub", "mini": "/mini"}


@app.get("/mini", response_class=HTMLResponse)
async def mini(request: Request):
    db = get_session()
    try:
        resp = templates.TemplateResponse(
            request,
            "mini.html",
            {"stars": plan_stars(db, "year"), "usdt": f"{plan_usdt(db, 'year'):g}"},
        )
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        return resp
    finally:
        db.close()


@app.get("/api/mini/me")
async def mini_me(user_id: int = 0, init_data: str = "", username: str = "", display_name: str = ""):
    uid = _uid(user_id=user_id, init_data=init_data)
    if not uid:
        return JSONResponse({"error": "未登录"}, status_code=401)
    blocked = await deny_json(uid)
    if blocked:
        return blocked
    db = get_session()
    try:
        tenant = get_or_create_tenant(db, uid)
        info = user_from_init(init_data)
        user_obj = SimpleNamespace(
            id=uid,
            username=username or info.get("username") or None,
            full_name=display_name or info.get("full_name") or "",
        )
        if not tenant_usable(tenant):
            activated = fulfill_stars_order(db, user_id=uid, user=user_obj)
            if activated:
                tenant = activated
        paid = tenant_usable(tenant)
        if paid:
            save_paid_profile(db, tenant, user_obj)
        ident = db.scalar(select(Identity).where(Identity.tenant_id == tenant.id)) or tenant.identity
        until = fmt_until(tenant.paid_until) if tenant.paid_until else ("管理员" if paid else "")
        return {
            "ok": True,
            "paid": paid,
            "is_admin": uid in ADMIN_TG_IDS,
            "plan": tenant.plan,
            "plan_label": PLANS.get(tenant.plan, {}).get("label", tenant.plan or "—"),
            "paid_until": until or "—",
            "username": ident.username if ident else "",
            "display_name": ident.display_name if ident else "",
            "card_text": ident.card_text if ident else "",
            "official_user_id": ident.official_user_id if ident else None,
        }
    finally:
        db.close()


@app.get("/api/mini/lookup")
async def mini_lookup(q: str = "", user_id: int = 0, init_data: str = ""):
    # Public search; optional deny check only when init_data verifies (never bare user_id).
    uid = _uid(user_id=user_id, init_data=init_data)
    if uid:
        blocked = await deny_json(uid)
        if blocked:
            return blocked
    raw = (q or "").strip()
    name = parse_username(raw)
    token = name or raw.lstrip("@")
    if not token:
        return JSONResponse({"error": "请输入 @用户名"}, status_code=400)
    db = get_session()
    try:
        matches = []
        rows = list(
            db.scalars(
                select(Identity).where(
                    (Identity.username.ilike(f"%{token}%")) | (Identity.display_name.ilike(f"%{token}%"))
                ).limit(15)
            )
        )
        for ident in rows:
            tenant = db.get(Tenant, ident.tenant_id)
            if tenant and tenant_usable(tenant) and ident.username:
                matches.append({
                    "username": ident.username,
                    "display_name": ident.display_name or "",
                    "official_user_id": ident.official_user_id,
                })
        ident = await resolve_paid_identity(db, name or token, platform_app.bot if platform_app else None)
        if ident:
            return {
                "ok": True,
                "found": True,
                "query": ident.username or token,
                "card": card_text(ident, db=db),
                "display_name": ident.display_name,
                "username": ident.username,
                "official_user_id": ident.official_user_id,
                "note": ident.card_text,
                "matches": matches,
            }
        return {
            "ok": True,
            "found": False,
            "query": token,
            "card": promo_text(bot_name="", name=token, db=db),
            "matches": matches,
        }
    finally:
        db.close()


# NOTE: rest of file continues in follow-up commit if truncated — DO NOT USE THIS STUB
