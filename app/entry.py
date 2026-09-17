from __future__ import annotations

from fastapi.responses import JSONResponse

from app.access import gate_user, subscribe_kb


async def deny_message(message, user_id: int) -> bool:
    reason, url = await gate_user(user_id)
    if not reason:
        return False
    await message.reply_text(reason, reply_markup=subscribe_kb(url))
    return True


async def deny_json(user_id: int):
    reason, url = await gate_user(user_id)
    if not reason:
        return None
    return JSONResponse({"error": reason, "channel": url}, status_code=403)
