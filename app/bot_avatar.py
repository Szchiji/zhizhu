from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

router = APIRouter()


@router.get("/avatar")
async def serve_avatar():
    from app import main as app_main

    application = getattr(app_main, "platform_app", None)
    bot = getattr(application, "bot", None) if application else None
    if not bot:
        raise HTTPException(status_code=404, detail="bot not ready")
    try:
        photos = await bot.get_user_profile_photos(bot.id, limit=1)
        if not photos.photos:
            raise HTTPException(status_code=404, detail="no photo")
        file = await bot.get_file(photos.photos[0][-1].file_id)
        data = await file.download_as_bytearray()
        return Response(
            content=bytes(data),
            media_type="image/jpeg",
            headers={
                "Cache-Control": "no-store, no-cache, max-age=0",
                "Pragma": "no-cache",
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
