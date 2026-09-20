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
from app.verify import card_text

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
                "card": card_text(ident),
                "display_name": ident.display_name,
                "username": ident.username,
                "official_user_id": ident.official_user_id,
                "note": ident.card_text,
                "matches": matches,
            }
        return {"ok": True, "found": False, "query": token, "matches": matches}
    finally:
        db.close()


@app.get("/api/mini/orders")
async def mini_orders(user_id: int = 0, init_data: str = ""):
    uid = _uid(user_id=user_id, init_data=init_data)
    if not uid:
        return JSONResponse({"error": "未登录"}, status_code=401)
    db = get_session()
    try:
        tenant = get_or_create_tenant(db, uid)
        rows = db.scalars(select(Order).where(Order.tenant_id == tenant.id).order_by(Order.id.desc()).limit(20))
        out = []
        for o in rows:
            out.append(
                {
                    "code": o.public_code,
                    "rail": o.rail,
                    "plan": o.plan,
                    "amount": f"{float(o.amount):g}",
                    "status": o.status,
                    "txid": o.txid or "",
                    "created": o.created_at.strftime("%m-%d %H:%M") if o.created_at else "",
                }
            )
        return {"ok": True, "orders": out}
    finally:
        db.close()


@app.post("/api/mini/profile")
async def mini_profile(request: Request):
    body = await request.json()
    uid = _uid(body)
    if not uid:
        return JSONResponse({"error": "未登录"}, status_code=401)
    blocked = await deny_json(uid)
    if blocked:
        return blocked
    db = get_session()
    try:
        tenant = get_or_create_tenant(db, uid)
        if not tenant_usable(tenant):
            return JSONResponse({"error": "开通后才能修改资料"}, status_code=403)
        ident = db.scalar(select(Identity).where(Identity.tenant_id == tenant.id)) or Identity(tenant_id=tenant.id)
        if "display_name" in body:
            ident.display_name = str(body.get("display_name") or "")[:64]
        if "card_text" in body:
            ident.card_text = str(body.get("card_text") or "")[:2000]
        if body.get("username"):
            ident.username = str(body.get("username")).lstrip("@")
        ident.official_user_id = ident.official_user_id or uid
        db.add(ident)
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@app.post("/api/mini/order")
async def mini_order(request: Request):
    body = await request.json()
    uid = _uid(body)
    key = str(body.get("plan") or "year")
    rail = str(body.get("rail") or "stars")
    if key not in PLANS:
        key = "year"
    if not uid:
        raise HTTPException(400, detail="bad user")
    blocked = await deny_json(uid)
    if blocked:
        return blocked
    if not PLATFORM_BOT_TOKEN:
        raise HTTPException(503, detail="bot not ready")
    db = get_session()
    try:
        tenant = get_or_create_tenant(db, uid)
        info = user_from_init(str(body.get("init_data") or ""))
        save_paid_profile(
            db,
            tenant,
            SimpleNamespace(
                id=uid,
                username=body.get("username") or info.get("username") or None,
                full_name=body.get("display_name") or info.get("full_name") or "",
            ),
        )
        _drop_open_orders(db, tenant.id)
        if rail == "usdt":
            addr = get_setting(db, "usdt_address", USDT_ADDRESS)
            if not addr:
                return JSONResponse({"error": "尚未配置 USDT 地址"}, status_code=400)
            code = new_code()
            amount = unique_usdt_amount(db, plan_usdt(db, key))
            db.add(
                Order(
                    public_code=code,
                    tenant_id=tenant.id,
                    rail="usdt",
                    plan=key,
                    period_days=PLANS[key]["days"],
                    amount=amount,
                    currency="USDT",
                    chain=USDT_CHAIN,
                    pay_address=addr,
                    status="pending",
                    expires_at=utcnow() + timedelta(minutes=20),
                )
            )
            db.commit()
            return {
                "ok": True,
                "code": code,
                "amount": f"{amount:g}",
                "address": addr,
                "chain": USDT_CHAIN,
            }
        price = plan_stars(db, key)
        payload = f"stars:{key}:{tenant.id}:{new_code()}"
        db.add(
            Order(
                public_code=new_code(),
                tenant_id=tenant.id,
                rail="stars",
                plan=key,
                period_days=PLANS[key]["days"],
                amount=price,
                currency="XTR",
                status="pending",
                payload=payload,
                expires_at=utcnow() + timedelta(hours=24),
            )
        )
        db.commit()
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{PLATFORM_BOT_TOKEN}/createInvoiceLink",
                json={
                    "title": f"官方核验·{PLANS[key]['label']}",
                    "description": "开通后可保存官方资料",
                    "payload": payload,
                    "provider_token": "",
                    "currency": "XTR",
                    "prices": [{"label": PLANS[key]["label"], "amount": price}],
                },
            )
            data = r.json()
        if not data.get("ok"):
            return JSONResponse({"error": data.get("description", "无法创建 Stars 账单")}, status_code=400)
        return {"ok": True, "invoice": data["result"], "payload": payload}
    finally:
        db.close()


@app.post("/api/mini/stars-paid")
async def mini_stars_paid(request: Request):
    body = await request.json()
    uid = _uid(body)
    if not uid:
        return JSONResponse({"error": "未登录"}, status_code=401)
    db = get_session()
    try:
        info = user_from_init(str(body.get("init_data") or ""))
        tenant = fulfill_stars_order(
            db,
            user_id=uid,
            payload=str(body.get("payload") or ""),
            user=SimpleNamespace(
                id=uid,
                username=body.get("username") or info.get("username") or None,
                full_name=body.get("display_name") or info.get("full_name") or "",
            ),
        )
        if not tenant:
            return JSONResponse({"error": "等待支付确认或订单不存在"}, status_code=404)
        return {"ok": True, "paid": True, "paid_until": fmt_until(tenant.paid_until)}
    finally:
        db.close()


@app.post("/wh/platform")
async def platform_hook(request: Request, x_telegram_bot_api_secret_token: str | None = Header(default=None)):
    _check_secret(x_telegram_bot_api_secret_token)
    if not platform_app:
        raise HTTPException(503, "platform bot not ready")
    data = await request.json()
    update = Update.de_json(data, platform_app.bot)
    await platform_app.process_update(update)
    return JSONResponse({"ok": True})


@app.post("/wh/t/{tenant_id}")
async def tenant_hook(tenant_id: int, request: Request, x_telegram_bot_api_secret_token: str | None = Header(default=None)):
    _check_secret(x_telegram_bot_api_secret_token)
    db = get_session()
    try:
        tenant = db.get(Tenant, tenant_id)
        if not tenant or not tenant.bot_token_enc:
            raise HTTPException(404, "tenant not found")
        token = decrypt_token(tenant.bot_token_enc)
        bot = Bot(token)
        data = await request.json()
        update = Update.de_json(data, bot)
        await handle_tenant_update(update, tenant, bot)
        return JSONResponse({"ok": True})
    finally:
        db.close()


@app.get("/pay/usdt/{code}", response_class=HTMLResponse)
async def pay_usdt(request: Request, code: str):
    db = get_session()
    try:
        order = db.scalar(select(Order).where(Order.public_code == code.upper()))
        if not order:
            return PlainTextResponse("订单不存在", status_code=404)
        return templates.TemplateResponse(
            request,
            "usdt.html",
            {
                "order": order,
                "amount": float(order.amount),
                "chain": order.chain or USDT_CHAIN,
                "address": order.pay_address or USDT_ADDRESS,
            },
        )
    finally:
        db.close()


@app.post("/api/usdt/confirm")
async def usdt_confirm(request: Request):
    """Manual USDT confirm. Requires shared secret; rate-limited; audited."""
    client_ip = _client_ip(request)
    body = await request.json()
    code = str(body.get("code", "")).upper().strip()
    txid = body.get("txid")

    def _slog(outcome: str, **extra) -> None:
        bits = " ".join(f"{k}={v}" for k, v in extra.items() if v is not None)
        log.info("usdt_confirm outcome=%s ip=%s code=%s %s", outcome, client_ip, code or "-", bits)

    if not _usdt_confirm_limiter.allow(
        f"ip:{client_ip}",
        limit=USDT_CONFIRM_IP_LIMIT,
        window_sec=USDT_CONFIRM_IP_WINDOW,
    ):
        _slog("rate_limited_ip")
        raise HTTPException(429, "rate limited")

    # Fail closed: empty secret must not allow anonymous confirms.
    if not USDT_CONFIRM_SECRET:
        _slog("secret_not_configured")
        raise HTTPException(503, "confirm secret not configured")
    if body.get("secret") != USDT_CONFIRM_SECRET:
        _slog("bad_secret")
        raise HTTPException(403, "bad secret")

    db = get_session()
    try:
        order = db.scalar(select(Order).where(Order.public_code == code)) if code else None

        if code and not _usdt_confirm_limiter.allow(
            f"code:{code}",
            limit=USDT_CONFIRM_CODE_LIMIT,
            window_sec=USDT_CONFIRM_CODE_WINDOW,
        ):
            if order:
                audit_order_event(db, order, "confirm_rate_limited")
                db.commit()
            _slog("rate_limited_code", order_id=order.id if order else None)
            raise HTTPException(429, "rate limited")

        if not order:
            _slog("unknown_order")
            raise HTTPException(404, "order not found")

        if order.rail != "usdt":
            audit_order_event(db, order, "confirm_denied_wrong_rail")
            db.commit()
            _slog("wrong_rail", order_id=order.id, rail=order.rail)
            raise HTTPException(400, "not a usdt order")

        if order.status == "active":
            audit_order_event(db, order, "confirm_idempotent")
            db.commit()
            _slog("already_active", order_id=order.id)
            return {"ok": True, "already": True}

        if order.status not in {"pending", "confirming", "paid", "draft"}:
            audit_order_event(db, order, "confirm_denied_bad_status")
            db.commit()
            _slog("bad_status", order_id=order.id, status=order.status)
            raise HTTPException(400, f"order status {order.status} not confirmable")

        if txid:
            order.txid = str(txid)[:128]
        add_event(db, order, "paid", "api_confirm")
        tenant = activate_order(db, order)
        _slog("ok", order_id=order.id, tenant_id=tenant.id)
        return {"ok": True, "paid_until": str(tenant.paid_until)}
    finally:
        db.close()
