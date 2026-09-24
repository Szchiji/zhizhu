"""Wave6: healthz depth, settings export redaction, assemble script."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.db import get_session, init_db
from app.health import health_payload
from app.services import set_setting
from app.wave6_settings_export import is_secret_key, redact_settings


def setup_function():
    init_db()


def test_secret_key_redaction():
    assert is_secret_key("bot_token_enc")
    assert is_secret_key("usdt_confirm_secret")
    assert is_secret_key("api_key")
    assert not is_secret_key("membership_plans")
    assert not is_secret_key("home_title")
    out = redact_settings({"home_title": "Hi", "clone_bot_token": "x", "usdt_address": "Txx"})
    assert out["home_title"] == "Hi"
    assert out["clone_bot_token"] == "***REDACTED***"
    assert out["usdt_address"] == "Txx"


def test_healthz_shape():
    import asyncio

    payload = asyncio.run(health_payload())
    assert "ok" in payload
    assert "db" in payload and "ok" in payload["db"]
    assert "redis" in payload
    assert "usdt_watch" in payload


def test_healthz_http():
    import app.main as main

    with TestClient(main.app) as client:
        r = client.get("/healthz")
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert "db" in data
    assert "redis" in data


def test_settings_export_forbidden(monkeypatch):
    import app.admin_ops as admin_ops
    import app.main as main

    monkeypatch.setattr(admin_ops, "_admin_id", lambda *a, **k: 0)
    with TestClient(main.app) as client:
        assert client.get("/api/mini/admin/settings/export").status_code == 403


def test_settings_export_redacts(monkeypatch):
    import app.admin_ops as admin_ops
    import app.admin_roles as roles
    import app.main as main
    import app.wave6_settings_export as w6

    init_db()
    db = get_session()
    try:
        set_setting(db, "home_title", "欢迎")
        set_setting(db, "some_bot_token", "SECRETVALUE")
        set_setting(db, "membership_plans", "[]")
    finally:
        db.close()

    monkeypatch.setattr(admin_ops, "_admin_id", lambda *a, **k: 42)
    monkeypatch.setattr(roles, "assert_cap", lambda *a, **k: None)
    monkeypatch.setattr(roles, "role_of", lambda *a, **k: "owner")
    monkeypatch.setattr(w6, "assert_cap", lambda *a, **k: None)
    monkeypatch.setattr(w6, "role_of", lambda *a, **k: "owner")
    with TestClient(main.app) as client:
        r = client.get("/api/mini/admin/settings/export")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("ok") is True
    settings = data["settings"]
    assert settings.get("home_title") == "欢迎"
    assert settings.get("some_bot_token") == "***REDACTED***"
    assert settings.get("membership_plans") == "[]"


def test_assemble_script_runs():
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "assemble_chunks.py"
    out = subprocess.check_output([sys.executable, str(script), "admin"], cwd=root)
    assert b"mount_admin" in out or b"def " in out
    assert len(out) > 1000


def test_chunk_docs_exist():
    assert Path("docs/CHUNKED_SOURCES.md").is_file()
    assert Path("scripts/assemble_chunks.py").is_file()
