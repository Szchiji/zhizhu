from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from app.config import PLATFORM_BOT_TOKEN, TOKEN_ENC_KEY


def _fernet() -> Fernet:
    raw = TOKEN_ENC_KEY or PLATFORM_BOT_TOKEN or "dev-key"
    digest = hashlib.sha256(raw.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_token(token: str) -> str:
    return _fernet().encrypt(token.encode()).decode()


def decrypt_token(blob: str) -> str:
    return _fernet().decrypt(blob.encode()).decode()
