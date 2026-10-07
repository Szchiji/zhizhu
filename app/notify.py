from __future__ import annotations

import logging

from app.config import ADMIN_TG_IDS
from app.services import fmt_until

log = logging.getLogger("zhizhu.notify")


def format_activation_text(tenant, order, *, paid_label: str = "", username: str = "") -> str:
    label = (paid_label or "").strip() or (getattr(order, "plan", None) or "套餐")
    try:
        amount = f"{float(order.amount):g}" if order is not None else "?"
    except (TypeError, ValueError):
        amount = "?"
    rail = (getattr(order, "rail", None) or "?").upper()
    code = getattr(order, "public_code", None) or "?"
    tg_id = getattr(tenant, "owner_tg_id", None) or "?"
    uname = (username or "").strip().lstrip("@")
    if not uname:
        ident = getattr(tenant, "identity", None)
        if ident and getattr(ident, "username", None):
            uname = str(ident.username).lstrip("@")
    until = fmt_until(tenant.paid_until) if tenant and getattr(tenant, "paid_until", None) else "—"
    user_line = f"用户：{tg_id}" + (f" @{uname}" if uname else "")
    return "\n".join(
        [
            "开通成功通知",
            f"通道：{rail}",
            f"金额：{amount}",
            f"套餐：{label}",
            f"订单：{code}",
            user_line,
            f"有效期至：{until}",
        ]
    )


async def notify_admins_activation(bot, tenant, order, *, paid_label: str = "", username: str = "") -> None:
    """DM every ADMIN_TG_IDS about a successful activation. Never raises to caller."""
    if not bot or not ADMIN_TG_IDS:
        return
    try:
        text = format_activation_text(tenant, order, paid_label=paid_label, username=username)
    except Exception as exc:
        log.warning("admin activation notify format failed: %s", exc)
        return
    for admin_id in sorted(ADMIN_TG_IDS):
        try:
            await bot.send_message(chat_id=admin_id, text=text)
        except Exception as exc:
            log.warning("admin activation notify failed admin=%s: %s", admin_id, exc)
    try:
        from app.db import get_session
        from app.referral import grant_referral
        from app.wave5_onboarding import maybe_send_onboarding_dm

        db = get_session()
        try:
            days = grant_referral(db, tenant)
            if bot and getattr(tenant, "owner_tg_id", None):
                try:
                    from app.referral import get_bind
                    from app.services import get_setting

                    bind = get_bind(db, int(tenant.owner_tg_id))
                    inviter_tg = int(bind["inviter"]) if bind and bind.get("inviter") else 0
                    if not inviter_tg:
                        raw = get_setting(db, f"invitee:{int(tenant.owner_tg_id)}")
                        if raw and str(raw).isdigit():
                            inviter_tg = int(raw)
                    if inviter_tg:
                        if days:
                            msg = f"🎁 你的好友已开通，+{days} 天已到账"
                        else:
                            msg = "好友已开通，邀请进度 +1"
                        await bot.send_message(chat_id=inviter_tg, text=msg)
                except Exception:
                    pass
            await maybe_send_onboarding_dm(bot, db, tenant)
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        log.warning("onboarding/referral hook failed: %s", exc)
