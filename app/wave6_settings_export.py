"""Wave6: admin settings JSON export with secret redaction."""
from __future__ import annotations

import logging
import re

from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.admin_roles import assert_cap, role_of
from app.db import get_session
from app.models import Setting
from app.services import add_admin_audit

log = logging.getLogger("zhizhu.wave6")

_SECRET_RE = re.compile(
    r"(token|secret|password|passwd|api[_-]?key|private|enc[_-]?key|bot_token)",
    re.I,
)


def is_secret_key(key: str) -> bool:
    return bool(_SECRET_RE.search(key or ""))


def redact_settings(rows: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in rows.items():
        if is_secret_key(k):
            out[k] = "***REDACTED***"
        else:
            out[k] = v
    return out


def _admin_uid(user_id: int = 0, init_data: str = "", body=None) -> int:
    try:
        from app import admin_ops

        return int(admin_ops._admin_id(user_id=user_id, init_data=init_data, body=body) or 0)
    except TypeError:
        try:
            from app import admin_ops

            return int(admin_ops._admin_id(user_id=user_id, init_data=init_data) or 0)
        except Exception:  # noqa: BLE001
            return 0
    except Exception:  # noqa: BLE001
        return 0


def mount_wave6(app) -> None:
    @app.get("/api/mini/admin/settings/export")
    async def settings_export(user_id: int = 0, init_data: str = ""):
        admin = _admin_uid(user_id=user_id, init_data=init_data)
        if not admin:
            return JSONResponse({"error": "仅管理员"}, status_code=403)
        db = get_session()
        try:
            err = assert_cap(db, admin, "export")
            if err:
                return JSONResponse({"error": err}, status_code=403)
            rows = {r.key: (r.value or "") for r in db.scalars(select(Setting)).all()}
            data = redact_settings(rows)
            add_admin_audit(
                db,
                admin,
                "settings_export",
                target_type="settings",
                target_id="json",
                detail=f"keys={len(data)} role={role_of(db, admin)}",
            )
            db.commit()
            return {"ok": True, "settings": data, "redacted": True}
        finally:
            db.close()
