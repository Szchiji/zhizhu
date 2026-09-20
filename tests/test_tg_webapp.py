"""HMAC WebApp init_data: accept valid, reject forged / user_id-only."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from app import tg_webapp

BOT = "123456789:AATestTokenForVerifyHubHMAC"


def _sign(pairs: dict[str, str], token: str = BOT) -> str:
    data_check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    return hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()


def _init_data(user: dict, *, token: str = BOT, bad_hash: str | None = None) -> str:
    pairs = {
        "auth_date": str(int(time.time())),
        "query_id": "AAEtest",
        "user": json.dumps(user, separators=(",", ":")),
    }
    digest = bad_hash if bad_hash is not None else _sign(pairs, token)
    return urlencode({**pairs, "hash": digest})


@pytest.fixture(autouse=True)
def _token(monkeypatch):
    monkeypatch.setattr(tg_webapp, "PLATFORM_BOT_TOKEN", BOT)


def test_require_webapp_user_accepts_valid_init_data():
    init = _init_data({"id": 42, "first_name": "Ada", "username": "ada"})
    assert tg_webapp.require_webapp_user(init_data=init) == 42
    assert tg_webapp.user_from_init(init)["username"] == "ada"


def test_require_webapp_user_rejects_forged_hash():
    init = _init_data({"id": 42, "first_name": "Ada"}, bad_hash="0" * 64)
    assert tg_webapp.require_webapp_user(init_data=init) == 0


def test_require_webapp_user_rejects_user_id_only_body():
    assert tg_webapp.require_webapp_user(init_data="", body={"user_id": 42}) == 0
    assert tg_webapp.require_webapp_user(init_data="", body={}) == 0
