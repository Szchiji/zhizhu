import os
from dotenv import load_dotenv

load_dotenv()


def _ids(value: str) -> set[int]:
    out = set()
    for part in (value or "").split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out


PLATFORM_BOT_TOKEN = os.getenv("PLATFORM_BOT_TOKEN", "")
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "").rstrip("/")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", WEBHOOK_BASE_URL).rstrip("/")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "zhizhu-dev-secret")
TOKEN_ENC_KEY = os.getenv("TOKEN_ENC_KEY", "")
ADMIN_TG_IDS = _ids(os.getenv("ADMIN_TG_IDS", ""))
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./zhizhu.sqlite3")

BRAND_NAME = os.getenv("BRAND_NAME", "")
BRAND_TITLE = os.getenv("BRAND_TITLE", "平台身份登记")
BOT_USERNAME = os.getenv("BOT_USERNAME", "").lstrip("@")
MENU_TEXT = os.getenv("MENU_TEXT", "小程序")

STARS_MONTHLY = int(os.getenv("STARS_MONTHLY", "500"))
USDT_YEARLY = float(os.getenv("USDT_YEARLY", "99"))
USDT_CHAIN = os.getenv("USDT_CHAIN", "trc20")
USDT_ADDRESS = os.getenv("USDT_ADDRESS", "")
USDT_CONFIRM_SECRET = os.getenv("USDT_CONFIRM_SECRET", "")
# In-memory rate limits for POST /api/usdt/confirm (per process; see app/rate_limit.py)
USDT_CONFIRM_IP_LIMIT = int(os.getenv("USDT_CONFIRM_IP_LIMIT", "20"))
USDT_CONFIRM_IP_WINDOW = int(os.getenv("USDT_CONFIRM_IP_WINDOW", "60"))
USDT_CONFIRM_CODE_LIMIT = int(os.getenv("USDT_CONFIRM_CODE_LIMIT", "10"))
USDT_CONFIRM_CODE_WINDOW = int(os.getenv("USDT_CONFIRM_CODE_WINDOW", "60"))

TRIAL_DAYS = int(os.getenv("TRIAL_DAYS", "0"))
PLAN_DEFAULT = os.getenv("PLAN_DEFAULT", "year")
PORT = int(os.getenv("PORT", "8080"))
