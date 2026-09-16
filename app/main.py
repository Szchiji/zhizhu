from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from telegram import Bot, Update

from app.config import (
    PLATFORM_BOT_TOKEN,
    USDT_ADDRESS,
    USDT_CHAIN,
    USDT_CONFIRM_SECRET,
    WEBHOOK_BASE_URL,
    WEBHOOK_SECRET,
)
from app.crypto_token import decrypt_token
from app.db import get_session, init_db
from app.models import Order, Tenant
from app.platform_bot import build_platform_app
from app.services import activate_order, add_event
from app.tenant_bot import handle_tenant_update

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("zhizhu")
templates = Jinja2Templates(directory="app/templates")
platform_app = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global platform_app
    init_db()
    if not PLATFORM_BOT_TOKEN:
        log.warning("PLATFORM_BOT_TOKEN missing")
        yield
        return
    platform_app = build_platform_app(PLATFORM_BOT_TOKEN)
    await platform_app.initialize()
    await platform_app.start()
    if WEBHOOK_BASE_URL:
        url = f"{WEBHOOK_BASE_URL}/wh/platform"
        await platform_app.bot.set_webhook(url=url, secret_token=WEBHOOK_SECRET, drop_pending_updates=False)
        log.info("platform webhook %s", url)
    yield
    if platform_app:
        await platform_app.stop()
        await platform_app.shutdown()


app = FastAPI(title="Zhizhu VerifyHub", lifespan=lifespan)


def _check_secret(secret: str | None) -> None:
    if WEBHOOK_SECRET and secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="bad secret")


@app.get("/healthz")
async def healthz():
    return {"ok": True}


@app.get("/")
async def root():
    return {"name": "zhizhu", "docs": "see README"}


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
