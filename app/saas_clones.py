"""Wave10 SaaS MVP: admin list/toggle of clone-bot instances (white-label).

Does NOT redefine Tenant as org SaaS \u2014 Tenant remains paying membership +
optional BotFather clone. No reseller billing, Stripe, or custom domains.
"""
from __future__ import annotations

import json
from typing import Any

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import or_, select

from app.config import ADMIN_TG_IDS, WEBHOOK_BASE_URL, WEBHOOK_SECRET
from app.crypto_token import decrypt_token
from app.db import get_session
from app.models import Identity, Tenant
from app.services import add_admin_audit, fmt_until, get_setting, set_setting, tenant_usable
from app.tg_webapp import require_webapp_user

DISABLED_KEY = "clone_disabled_ids"


def _admin(body: dict | None = None, user_id: int = 0, init_data: str = "") -> int:
    del user_id
    uid = require_webapp_user(init_data=init_data, body=body)
    return uid if uid in ADMIN_TG_IDS else 0


def load_disabled_ids(db) -> set[int]:
    raw = (get_setting(db, DISABLED_KEY, "") or "").strip()
    if not raw:
        return set()
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return {int(x) for x in data if str(x).strip().lstrip("-").isdigit()}
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    out: set[int] = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out


def save_disabled_ids(db, ids: set[int]) -> None:
    cleaned = sorted({int(x) for x in ids if int(x) > 0})
    set_setting(db, DISABLED_KEY, json.dumps(cleaned, ensure_ascii=False))


def is_clone_disabled(db, tenant_id: int) -> bool:
    return int(tenant_id) in load_disabled_ids(db)


def expected_webhook_url(tenant_id: int) -> str:
    base = (WEBHOOK_BASE_URL or "").rstrip("/")
    if not base:
        return ""
    return f"{base}/wh/t/{int(tenant_id)}"


def _serialize(tenant: Tenant, identity: Identity | None, disabled: set[int]) -> dict[str, Any]:
    tid = int(tenant.id)
    has_token = bool(tenant.bot_token_enc)
    usable = tenant_usable(tenant)
    return {
        "tenant_id": tid,
        "owner_tg_id": int(tenant.owner_tg_id),
        "bot_id": int(tenant.bot_id) if tenant.bot_id else None,
        "bot_username": tenant.bot_username or "",
        "has_token": has_token,
        "status": tenant.status,
        "plan": tenant.plan,
        "paid_until": tenant.paid_until.isoformat() + "Z" if tenant.paid_until else None,
        "paid_until_label": fmt_until(tenant.paid_until) if tenant.paid_until else "\u2014",
        "usable": usable,
        "clone_enabled": has_token and tid not in disabled,
        "webhook_url": expected_webhook_url(tid) if has_token else "",
        "display_name": (identity.display_name if identity else "") or "",
        "username": (identity.username if identity else "") or "",
    }


def list_clone_instances(db, *, only_with_bot: bool = True) -> list[dict[str, Any]]:
    disabled = load_disabled_ids(db)
    q = select(Tenant, Identity).outerjoin(Identity, Identity.tenant_id == Tenant.id)
    if only_with_bot:
        q = q.where(
            or_(
                Tenant.bot_token_enc.isnot(None),
                Tenant.bot_id.isnot(None),
                Tenant.bot_username.isnot(None),
            )
        )
    q = q.order_by(Tenant.id.desc())
    rows = db.execute(q).all()
    out = []
    for tenant, identity in rows:
        if only_with_bot and not (tenant.bot_token_enc or tenant.bot_id or tenant.bot_username):
            continue
        out.append(_serialize(tenant, identity, disabled))
    return out


async def _tg_webhook_info(token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"https://api.telegram.org/bot{token}/getWebhookInfo")
    data = r.json() if r.content else {}
    if not data.get("ok"):
        return {"ok": False, "error": (data.get("description") or "getWebhookInfo failed")}
    info = data.get("result") or {}
    return {
        "ok": True,
        "url": info.get("url") or "",
        "pending_update_count": info.get("pending_update_count"),
        "last_error_message": info.get("last_error_message") or "",
        "has_custom_certificate": bool(info.get("has_custom_certificate")),
    }


async def _tg_set_webhook(token: str, tenant_id: int) -> dict[str, Any]:
    url = expected_webhook_url(tenant_id)
    if not url:
        return {"ok": False, "error": "WEBHOOK_BASE_URL \u672a\u914d\u7f6e"}
    payload = {
        "url": url,
        "secret_token": WEBHOOK_SECRET,
        "allowed_updates": ["message", "callback_query", "inline_query"],
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"https://api.telegram.org/bot{token}/setWebhook", json=payload)
    data = r.json() if r.content else {}
    return {
        "ok": bool(data.get("ok")),
        "url": url,
        "error": "" if data.get("ok") else (data.get("description") or "setWebhook failed"),
    }


async def _tg_delete_webhook(token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            f"https://api.telegram.org/bot{token}/deleteWebhook",
            json={"drop_pending_updates": False},
        )
    data = r.json() if r.content else {}
    return {
        "ok": bool(data.get("ok")),
        "error": "" if data.get("ok") else (data.get("description") or "deleteWebhook failed"),
    }


def mount_saas_clones(app) -> None:
    @app.get("/api/mini/admin/clones")
    async def get_clones(user_id: int = 0, init_data: str = ""):
        if not _admin(user_id=user_id, init_data=init_data):
            return JSONResponse({"error": "\u4ec5\u7ba1\u7406\u5458"}, status_code=403)
        db = get_session()
        try:
            items = list_clone_instances(db)
            from app.plans import clone_on

            return {
                "ok": True,
                "clone_feature_on": clone_on(db),
                "webhook_base": (WEBHOOK_BASE_URL or "").rstrip("/"),
                "count": len(items),
                "clones": items,
                "hint": "\u53ea\u8bfb\u4f1a\u5458\u5b57\u6bb5 + \u542f\u505c\u514b\u9686\u5b9e\u4f8b\u3002\u4e0d\u505c\u7528\u5e73\u53f0\u8d26\u53f7\uff1b\u505c\u7528\u4ec5\u5207\u65ad\u767d\u6807\u673a\u5668\u4eba Webhook\u3002",
            }
        finally:
            db.close()

    @app.post("/api/mini/admin/clones")
    async def post_clones(request: Request):
        body = await request.json()
        admin = _admin(body=body)
        if not admin:
            return JSONResponse({"error": "\u4ec5\u7ba1\u7406\u5458"}, status_code=403)
        action = str(body.get("action") or "").strip().lower()
        tenant_id = body.get("tenant_id")
        try:
            tenant_id = int(tenant_id)
        except (TypeError, ValueError):
            return JSONResponse({"error": "\u8bf7\u63d0\u4f9b tenant_id"}, status_code=400)

        db = get_session()
        try:
            tenant = db.get(Tenant, tenant_id)
            if not tenant:
                return JSONResponse({"error": "\u79df\u6237\u4e0d\u5b58\u5728"}, status_code=404)
            if not tenant.bot_token_enc and action in {"enable", "disable", "webhook"}:
                return JSONResponse({"error": "\u8be5\u79df\u6237\u5c1a\u672a\u7ed1\u5b9a\u514b\u9686 Token"}, status_code=400)

            disabled = load_disabled_ids(db)
            tg_result: dict[str, Any] = {}
            token = ""
            if tenant.bot_token_enc:
                try:
                    token = decrypt_token(tenant.bot_token_enc)
                except Exception:  # noqa: BLE001
                    return JSONResponse({"error": "Token \u89e3\u5bc6\u5931\u8d25\uff0c\u8bf7\u7528\u6237\u91cd\u65b0\u7ed1\u5b9a"}, status_code=400)

            if action == "disable":
                disabled.add(tenant_id)
                save_disabled_ids(db, disabled)
                if token:
                    tg_result = await _tg_delete_webhook(token)
                add_admin_audit(
                    db,
                    admin,
                    "clone_disable",
                    target_type="tenant",
                    target_id=str(tenant_id),
                    detail=f"@{tenant.bot_username or ''};tg={tg_result}",
                )
                db.commit()
                return {
                    "ok": True,
                    "clone_enabled": False,
                    "telegram": tg_result,
                    "message": "\u5df2\u505c\u7528\u514b\u9686\u5b9e\u4f8b\uff08\u5df2\u5c1d\u8bd5\u5220\u9664 Webhook\uff09",
                }

            if action == "enable":
                disabled.discard(tenant_id)
                save_disabled_ids(db, disabled)
                if token:
                    tg_result = await _tg_set_webhook(token, tenant_id)
                add_admin_audit(
                    db,
                    admin,
                    "clone_enable",
                    target_type="tenant",
                    target_id=str(tenant_id),
                    detail=f"@{tenant.bot_username or ''};tg={tg_result}",
                )
                db.commit()
                return {
                    "ok": True,
                    "clone_enabled": True,
                    "telegram": tg_result,
                    "message": "\u5df2\u542f\u7528\u514b\u9686\u5b9e\u4f8b\uff08\u5df2\u5c1d\u8bd5\u8bbe\u7f6e Webhook\uff09",
                }

            if action == "webhook":
                if not token:
                    return JSONResponse({"error": "\u65e0 Token"}, status_code=400)
                info = await _tg_webhook_info(token)
                add_admin_audit(
                    db,
                    admin,
                    "clone_webhook",
                    target_type="tenant",
                    target_id=str(tenant_id),
                    detail=str(info)[:400],
                )
                db.commit()
                return {
                    "ok": True,
                    "expected_url": expected_webhook_url(tenant_id),
                    "webhook": info,
                    "clone_enabled": tenant_id not in disabled,
                }

            return JSONResponse({"error": "\u672a\u77e5 action\uff08enable/disable/webhook\uff09"}, status_code=400)
        finally:
            db.close()
