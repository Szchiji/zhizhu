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
from app.config import (
    ADMIN_TG_IDS,
    PLATFORM_BOT_TOKEN,
    PUBLIC_BASE_URL,
    USDT_ADDRESS,
    USDT_CHAIN,
    USDT_CONFIRM_SECRET,
    WEBHOOK_BASE_URL,
    WEBHOOK_SECRET,
)
from app.crypto_token import decrypt_token
from app.db import get_session, init_db
from app.models import Identity, Order, Tenant, utcnow
from app.plans import PLANS, plan_stars, plan_usdt
from app.platform_bot import build_platform_app
from app.services import (
    activate_order,
    add_event,
    find_paid_identity,
    fmt_until,
    get_or_create_tenant,
    get_setting,
    new_code,
    open_order,
    parse_username,
    save_paid_profile,
    tenant_usable,
)
from app.tenant_bot import handle_tenant_update
from app.tg_webapp import user_from_init, user_id_from_init
from app.usdt_watch import watch_loop
from app.verify import card_text

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("zhizhu")
templates = Jinja2Templates(directory="app/templates")
platform_app = None


def _uid(body: dict | None = None, user_id: int = 0, init_data: str = "") -> int:
    if init_data:
        n = user_id_from_init(init_data)
        if n:
            return n
    if body:
        n = user_id_from_init(str(body.get("init_data") or ""))
        if n:
            return n
        try:
            return int(body.get("user_id") or 0)
        except (TypeError, ValueError):
            return 0
    return int(user_id or 0)


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
    if WEBHOOK_BASE_URL:
        url = f"{WEBHOOK_BASE_URL}/wh/platform"
        await platform_app.bot.set_webhook(
            url=url,
            secret_token=WEBHOOK_SECRET,
            drop_pending_updates=False,
            allowed_updates=["message", "callback_query", "inline_query", "pre_checkout_query"],
        )
        log.info("platform webhook %s", url)
    mini = f"{(PUBLIC_BASE_URL or WEBHOOK_BASE_URL or '').rstrip('/')}/mini"
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
        return templates.TemplateResponse(
            request,
            "mini.html",
            {"stars": plan_stars(db, "year"), "usdt": f"{plan_usdt(db, 'year'):g}"},
        )
    finally:
        db.close()


@app.get("/api/mini/me")
async def mini_me(user_id: int = 0, init_data: str = "", username: str = "", display_name: str = ""):
    uid = _uid(user_id=user_id, init_data=init_data)
    if not uid:
        return JSONResponse({"error": "未登录"}, status_code=401)
    db = get_session()
    try:
        tenant = get_or_create_tenant(db, uid)
        paid = tenant_usable(tenant)
        info = user_from_init(init_data)
        if paid:
            save_paid_profile(
                db,
                tenant,
                SimpleNamespace(
                    id=uid,
                    username=username or info.get("username") or None,
                    full_name=display_name or info.get("full_name") or "",
                ),
            )
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
async def mini_lookup(q: str = ""):
    name = parse_username(q)
    if not name:
        return JSONResponse({"error": "请输入 @用户名"}, status_code=400)
    db = get_session()
    try:
        ident = find_paid_identity(db, name)
        if not ident:
            return {"ok": True, "found": False, "query": name}
        return {
            "ok": True,
            "found": True,
            "query": name,
            "card": card_text(ident),
            "display_name": ident.display_name,
            "username": ident.username,
            "official_user_id": ident.official_user_id,
            "note": ident.card_text,
        }
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
            amount = plan_usdt(db, key)
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
        return {"ok": True, "invoice": data["result"]}
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
    body = await request.json()
    if USDT_CONFIRM_SECRET and body.get("secret") != USDT_CONFIRM_SECRET:
        raise HTTPException(403, "bad secret")
    code = str(body.get("code", "")).upper()
    txid = body.get("txid")
    db = get_session()
    try:
        order = db.scalar(select(Order).where(Order.public_code == code))
        if not order:
            raise HTTPException(404, "order not found")
        if order.status == "active":
            return {"ok": True, "already": True}
        if txid:
            order.txid = txid
        add_event(db, order, "paid", "api_confirm")
        tenant = activate_order(db, order)
        return {"ok": True, "paid_until": str(tenant.paid_until)}
    finally:
        db.close()
