"""Wave4: admin roles capability checks."""
from __future__ import annotations

import json

from app.admin_roles import ACTION_CAP, assert_action_cap, has_cap, load_role_map, role_of
from app.db import get_session, init_db
from app.services import set_setting


def setup_function():
    init_db()


def test_role_caps_matrix():
    assert has_cap("owner", "users")
    assert has_cap("owner", "price")
    assert has_cap("ops", "price")
    assert has_cap("ops", "users")
    assert has_cap("support", "confirm")
    assert has_cap("support", "view")
    assert not has_cap("support", "price")
    assert not has_cap("support", "users")
    assert ACTION_CAP["plans"] == "price"
    assert ACTION_CAP["user_delete"] == "users"
    assert ACTION_CAP["confirm"] == "confirm"


def test_settings_role_override():
    db = get_session()
    try:
        set_setting(db, "admin_roles", json.dumps({"900001": "support", "900002": "ops"}))
        assert role_of(db, 900001) == "support"
        assert role_of(db, 900002) == "ops"
        assert assert_action_cap(db, 900001, "confirm") is None
        assert assert_action_cap(db, 900001, "plans") is not None
        assert assert_action_cap(db, 900002, "plans") is None
        assert assert_action_cap(db, 900002, "user_delete") is None
        mapping = load_role_map(db)
        assert mapping["900001"] == "support"
    finally:
        db.close()


def test_confirm_helper_in_mini_core():
    from pathlib import Path

    text = Path("app/templates/mini-core.js").read_text(encoding="utf-8")
    assert "function confirmAct" in text
    assert "user_delete" in text
    assert "确认改价" in text or "保存套餐" in text
