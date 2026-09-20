from __future__ import annotations

from app.platform_bot_helpers import *  # noqa: F403


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_user.id):
        await update.effective_message.reply_text('仅管理员可用。')
        return
    db = get_session()
    try:
        await _show_admin(update.effective_message, db)
    finally:
        db.close()


async def cmd_paid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_user.id):
        return
    db = get_session()
    try:
        rows = list(db.scalars(select(Tenant).order_by(Tenant.id.desc()).limit(40)))
        lines = ['已开通用户']
        for tenant in rows:
            if not tenant_usable(tenant):
                continue
            ident = tenant.identity
            uname = f'@{ident.username}' if ident and ident.username else '无用户名'
            lines.append(f'#{tenant.id}  TG {tenant.owner_tg_id}  {uname}  至 {fmt_until(tenant.paid_until) or "-"}')
        if len(lines) == 1:
            lines.append('暂无')
        lines.append('\n补登记：/bind 用户名')
        await update.effective_message.reply_text('\n'.join(lines))
    finally:
        db.close()


async def cmd_bind(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.effective_message.reply_text('用法：/bind 用户名\n或 /bind 用户名 电报ID')
        return
    name = parse_username(context.args[0]) or context.args[0].lstrip('@')
    tg_id = 0
    if len(context.args) > 1 and context.args[1].lstrip('-').isdigit():
        tg_id = int(context.args[1])
    db = get_session()
    try:
        if not tg_id:
            try:
                chat = await context.bot.get_chat('@' + name)
                tg_id = chat.id
            except Exception as exc:
                await update.effective_message.reply_text(f'电报查不到 @{name}\n{exc}\n改用 /bind {name} 电报ID')
                return
        tenant = db.scalar(select(Tenant).where(Tenant.owner_tg_id == tg_id))
        if not tenant:
            ident = db.scalar(select(Identity).where(Identity.official_user_id == tg_id))
            tenant = db.get(Tenant, ident.tenant_id) if ident else None
        if not tenant:
            await update.effective_message.reply_text(f'库里没有 TG {tg_id} 的开通记录。先发 /paid 看列表。')
            return
        ident = tenant.identity or Identity(tenant_id=tenant.id)
        ident.username = name
        ident.official_user_id = ident.official_user_id or tg_id
        if not ident.display_name:
            ident.display_name = name
        db.add(ident)
        add_admin_audit(
            db,
            update.effective_user.id,
            "user_bind",
            target_type="tenant",
            target_id=str(tenant.id),
            detail=f"tg_id={tenant.owner_tg_id};username={name}",
        )
        db.commit()
        await update.effective_message.reply_text(
            f'已补登记 @{name}\nTG {tenant.owner_tg_id}\n开通至 {fmt_until(tenant.paid_until) or "-"}'
        )
    finally:
        db.close()
