"""card_tpl.fill HTML-escapes dynamic placeholders (script tags)."""
from __future__ import annotations

from app.card_tpl import fill


def test_fill_escapes_script_in_dynamic_fields(monkeypatch):
    monkeypatch.setattr("app.card_tpl.brand_name", lambda: "VerifyHub")
    monkeypatch.setattr("app.card_tpl.bot_username", lambda: "verifyhub_bot")
    payload = "<script>alert(1)</script>"
    out = fill(
        "姓名：{姓名}\n账号：{账号}\n正文：{正文}\n查询：{查询词}",
        {
            "姓名": payload,
            "账号": payload,
            "正文": payload,
            "查询词": payload,
        },
    )
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    assert "alert(1)" in out


def test_fill_leaves_static_template_markup():
    out = fill("固定 <b>标题</b>：{姓名}", {"姓名": "张三"})
    assert out == "固定 <b>标题</b>：张三"
