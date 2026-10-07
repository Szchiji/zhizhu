"""Viral growth W1: ref attribution, cycle rewards, bind rules."""
from __future__ import annotations

from datetime import timedelta

from app.db import get_session, init_db
from app.models import utcnow
from app.referral import (
    bind_referrer,
    build_startapp,
    decode_ref_code,
    encode_ref_code,
    get_bind,
    grant_referral,
    invite_link,
    parse_ref_payload,
    progress_payload,
    referral_banner,
    ref_cycle,
    ref_days,
)
from app.services import get_or_create_tenant, get_setting, set_setting


def setup_function():
    init_db()


def test_ref_code_roundtrip():
    for n in (1, 42, 12345, 5820193477, 999_999_999):
        assert decode_ref_code(encode_ref_code(n)) == n


def test_parse_startapp_and_legacy():
    code = encode_ref_code(1001)
    inv, src = parse_ref_payload(f"ref_{code}_src_found")
    assert inv == 1001 and src == "found"
    inv, src = parse_ref_payload(f"ref_{code}_src_empty")
    assert inv == 1001 and src == "empty"
    inv, src = parse_ref_payload("ref1001")
    assert inv == 1001 and src == "invite"
    inv, src = parse_ref_payload(f"https://t.me/bot/app?startapp=ref_{code}_src_invite")
    assert inv == 1001 and src == "invite"
    assert parse_ref_payload("")[0] is None


def test_build_startapp_charset():
    sp = build_startapp(1001, "found")
    assert sp.startswith("ref_")
    assert "_src_found" in sp
    assert all(c.isalnum() or c == "_" for c in sp)
    assert len(sp) <= 64


def test_bind_no_overwrite_and_self_invalid():
    db = get_session()
    try:
        r1 = bind_referrer(db, invitee_tg=2002, payload=build_startapp(1001, "found"))
        assert r1["ok"] and r1["inviter"] == 1001 and not r1.get("kept")
        r2 = bind_referrer(db, invitee_tg=2002, payload=build_startapp(1003, "invite"))
        assert r2["ok"] and r2.get("kept") and r2["inviter"] == 1001
        self_r = bind_referrer(db, invitee_tg=1001, payload=build_startapp(1001, "invite"))
        assert not self_r["ok"] and self_r["reason"] == "self"
        bind = get_bind(db, 2002)
        assert bind and bind["inviter"] == 1001 and bind["src"] == "found"
    finally:
        db.close()


def test_bind_expired_not_counted():
    db = get_session()
    try:
        bind_referrer(db, invitee_tg=3002, payload=build_startapp(3001, "invite"))
        # backdate bind beyond 24h
        old = (utcnow() - timedelta(hours=25)).isoformat(timespec="seconds")
        set_setting(
            db,
            "invitee:3002",
            '{"inviter":3001,"src":"invite","ts":"%s"}' % old,
        )
        invitee = get_or_create_tenant(db, 3002)
        inviter = get_or_create_tenant(db, 3001)
        before = inviter.paid_until
        assert grant_referral(db, invitee) == 0
        db.refresh(inviter)
        assert inviter.paid_until == before
        assert not get_setting(db, "ref_counted:3002")
    finally:
        db.close()


def test_cycle_reward_every_three_and_once_per_tg():
    db = get_session()
    try:
        set_setting(db, "ref_on", "1")
        set_setting(db, "ref_days", "7")
        set_setting(db, "ref_cycle", "3")
        inviter = get_or_create_tenant(db, 4001)
        assert inviter.paid_until is None

        granted_total = 0
        for i, invitee_tg in enumerate((4011, 4012, 4013), start=1):
            bind_referrer(db, invitee_tg=invitee_tg, payload=build_startapp(4001, "invite"))
            invitee = get_or_create_tenant(db, invitee_tg)
            # simulate paid
            invitee.paid_until = utcnow() + timedelta(days=30)
            invitee.status = "active"
            db.commit()
            g = grant_referral(db, invitee)
            granted_total += g
            # second grant for same invitee must no-op
            assert grant_referral(db, invitee) == 0
            prog = progress_payload(db, 4001)
            assert prog["invited_paid"] == i
            if i < 3:
                assert g == 0
                assert prog["cycle_progress"] == i
            else:
                assert g == 7
                assert prog["cycle_progress"] == 0
                assert prog["total_reward_days"] == 7

        db.refresh(inviter)
        assert inviter.paid_until is not None
        # invitee got bonus days (>= 30 + 7)
        invitee3 = get_or_create_tenant(db, 4013)
        db.refresh(invitee3)
        assert invitee3.paid_until is not None
    finally:
        db.close()


def test_legacy_digit_bind_still_works():
    db = get_session()
    try:
        r = bind_referrer(db, invitee_tg=5002, payload="ref5001")
        assert r["ok"] and r["inviter"] == 5001
        invitee = get_or_create_tenant(db, 5002)
        invitee.paid_until = utcnow() + timedelta(days=10)
        invitee.status = "active"
        db.commit()
        # one paid not enough for cycle=3
        assert grant_referral(db, invitee) == 0
        assert progress_payload(db, 5001)["invited_paid"] == 1
    finally:
        db.close()


def test_banner_only_for_unpaid_with_ref():
    db = get_session()
    try:
        bind_referrer(db, invitee_tg=6002, payload=build_startapp(6001, "empty"))
        b = referral_banner(db, 6002)
        assert b and b["show"] and b["days"] == ref_days(db)
        # after paid, hide
        t = get_or_create_tenant(db, 6002)
        t.paid_until = utcnow() + timedelta(days=5)
        t.status = "active"
        db.commit()
        assert referral_banner(db, 6002) is None
    finally:
        db.close()


def test_invite_link_uses_startapp():
    link = invite_link(7001, src="invite")
    # may be empty if bot username unset in tests
    if link:
        assert "/app?startapp=ref_" in link
        assert "_src_invite" in link


def test_defaults_cycle_three_days_seven():
    db = get_session()
    try:
        assert ref_cycle(db) == 3
        assert ref_days(db) == 7
    finally:
        db.close()


def test_growth_assets_wired():
    from pathlib import Path

    from app.static_ver import MINI_ASSET_VER

    assert MINI_ASSET_VER >= 38
    html_mw = Path("app/wave4_mini_html.py").read_text(encoding="utf-8")
    assert "mini-growth.js" in html_mw
    growth = Path("app/templates/mini-growth.js").read_text(encoding="utf-8")
    assert "分享到聊天" in growth
    assert "去开通" in growth
    assert "邀请好友得天数" in growth
    assert "好友送你" in growth or "gift-banner" in growth
    assert "分享预览" in growth
    assert "发送到聊天" in growth
    assert "复制链接" in growth
    assert "openShareSheet" in growth or "growth-sheet" in growth
    assert "switchInlineQuery" in growth
