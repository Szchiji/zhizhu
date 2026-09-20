"""Card template persistence: save → load → fill/render uses saved settings."""
from __future__ import annotations

from types import SimpleNamespace
from datetime import datetime, timezone

from app.db import init_db, get_session
from app.card_tpl import (
    save_tpl,
    load_tpl,
    render,
    apply_pack,
    fill,
    sanitize_telegram_html,
    DEFAULTS,
)
from app.verify import card_text, promo_text


def test_sanitize_strips_disallowed_keeps_telegram_tags():
    raw = '<b>粗</b><script>x</script><i>斜</i><a href="https://t.me/x">链</a><img src=x>'
    out = sanitize_telegram_html(raw)
    assert "<b>粗</b>" in out
    assert "<i>斜</i>" in out
    assert '<a href="https://t.me/x">链</a>' in out
    assert "<script>" not in out
    assert "<img" not in out


def test_sanitize_drops_bad_href():
    out = sanitize_telegram_html('<a href="javascript:alert(1)">x</a>')
    assert "javascript" not in out
    assert "x" in out


def test_save_load_render_roundtrip(monkeypatch):
    monkeypatch.setattr("app.card_tpl.brand_name", lambda: "VerifyHub")
    monkeypatch.setattr("app.card_tpl.bot_username", lambda: "vh_bot")
    init_db()
    db = get_session()
    custom = "MARKER_SAVE\n姓名：{姓名}\n<b>加粗</b>\n{正文}"
    save_tpl(db, {"paid": custom, "unpaid": "UNPAID_MARK {查询词}", "issuer": "ISSUER_MARK", "parse": "html"})
    db.close()

    db2 = get_session()
    loaded = load_tpl(db2)
    assert "MARKER_SAVE" in loaded["paid"]
    assert "<b>加粗</b>" in loaded["paid"]
    assert loaded["parse"] == "html"
    # per-field keys exist
    from app.services import get_setting

    assert "MARKER_SAVE" in get_setting(db2, "card_tpl_paid", "")
    text = render("paid", {"姓名": "张三", "正文": "<script>"}, db=db2)
    assert "MARKER_SAVE" in text
    assert "张三" in text
    assert "<b>加粗</b>" in text
    assert "&lt;script&gt;" in text
    unpaid = render("unpaid", {"查询词": "@foo"}, db=db2)
    assert "UNPAID_MARK" in unpaid
    db2.close()


def test_apply_pack_then_custom_persists(monkeypatch):
    monkeypatch.setattr("app.card_tpl.brand_name", lambda: "VerifyHub")
    monkeypatch.setattr("app.card_tpl.bot_username", lambda: "vh_bot")
    init_db()
    db = get_session()
    apply_pack(db, "brief")
    loaded = load_tpl(db)
    assert loaded["pack"] == "brief"
    save_tpl(db, {"paid": "AFTER_PACK {姓名}", "unpaid": loaded["unpaid"], "issuer": loaded["issuer"]})
    again = load_tpl(get_session())
    assert again["paid"].startswith("AFTER_PACK")
    assert "AFTER_PACK" in render("paid", {"姓名": "A"}, db=get_session())


def test_card_text_uses_saved_tpl(monkeypatch):
    monkeypatch.setattr("app.card_tpl.brand_name", lambda: "VerifyHub")
    monkeypatch.setattr("app.card_tpl.bot_username", lambda: "vh_bot")
    init_db()
    db = get_session()
    save_tpl(db, {"paid": "CUSTOM_CARD {姓名} {有效期}", "unpaid": DEFAULTS["unpaid"], "issuer": DEFAULTS["issuer"]})
    until = datetime(2027, 6, 1, 8, 0, tzinfo=timezone.utc)
    tenant = SimpleNamespace(paid_until=until, status="active", owner_tg_id=1)
    ident = SimpleNamespace(
        card_text="备注",
        display_name="李四",
        username="li",
        official_user_id=42,
        tenant=tenant,
    )
    text = card_text(ident, db=db)
    assert "CUSTOM_CARD" in text
    assert "李四" in text
    assert "2027" in text
    promo = promo_text("vh_bot", "nobody", db=db)
    # unpaid still default-ish unless we overwrote — we kept DEFAULTS unpaid which has 尚未
    assert "尚未" in promo or "登记" in promo


def test_fill_still_escapes_dynamic():
    out = fill("x{姓名}", {"姓名": "<b>no</b>"})
    assert "&lt;b&gt;no&lt;/b&gt;" in out
