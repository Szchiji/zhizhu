"""Multi-plan membership pricing helpers and admin save."""
from __future__ import annotations

import json

from app.db import get_session, init_db
from app.plans import (
    ensure_plan_key,
    list_plans,
    normalize_plans,
    plan_info,
    plan_stars,
    plan_usdt,
    price_board,
    save_plan_defs,
    set_plan_price,
)
from app.services import get_setting, set_setting


def setup_function():
    init_db()


def test_default_single_year_plan_uses_legacy_settings():
    db = get_session()
    try:
        set_setting(db, "stars_year", "3200")
        set_setting(db, "usdt_year", "88")
        plans = list_plans(db)
        assert len(plans) == 1
        assert plans[0]["id"] == "year"
        assert plans[0]["days"] == 365
        assert plans[0]["label"] == "一年"
        assert plans[0]["stars"] == 3200
        assert plans[0]["usdt"] == 88.0
        assert ensure_plan_key(db, "month") == "year"
        assert "一年" in price_board(db)
    finally:
        db.close()


def test_save_and_list_multi_plans():
    db = get_session()
    try:
        saved = save_plan_defs(
            db,
            [
                {"id": "month", "label": "月付", "days": 30},
                {"id": "year", "label": "年付", "days": 365},
                {"id": "bad", "label": "x", "days": 0},  # dropped
                {"id": "MONTH", "label": "重复", "days": 31},  # dup id dropped
            ],
        )
        assert [p["id"] for p in saved] == ["month", "year"]
        set_plan_price(db, "month", "stars", 500)
        set_plan_price(db, "month", "usdt", 12.5)
        set_plan_price(db, "year", "stars", 4000)
        set_plan_price(db, "year", "usdt", 99)
        plans = list_plans(db)
        assert plans[0]["stars"] == 500
        assert plans[0]["usdt"] == 12.5
        assert plans[1]["stars"] == 4000
        assert get_setting(db, "stars_month") == "500"
        assert get_setting(db, "usdt_month") == "12.5"
        info = plan_info(db, "month")
        assert info["days"] == 30
        assert info["label"] == "月付"
        assert ensure_plan_key(db, "nope") == "year"
        assert plan_stars(db, "month") == 500
        assert plan_usdt(db, "month") == 12.5
        raw = get_setting(db, "membership_plans")
        assert json.loads(raw)[0]["id"] == "month"
    finally:
        db.close()


def test_normalize_plans_rejects_garbage():
    assert normalize_plans(None) == []
    assert normalize_plans("x") == []
    assert normalize_plans([{"id": "1bad", "days": 30}]) == []
    assert normalize_plans([{"id": "ok", "label": "好", "days": 7}]) == [
        {"id": "ok", "label": "好", "days": 7}
    ]
