"""Safe Alembic upgrade for Railway / Procfile start.

Existing production DBs were created via SQLAlchemy create_all and have no
alembic_version row. If core tables already exist, stamp head once, then
upgrade (no-op until the next revision). Fresh DBs run upgrade and create
tables from migrations.
"""
from __future__ import annotations

import logging
import sys

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

log = logging.getLogger("zhizhu.migrate")

_EXISTING_SENTINEL = "tenants"


def _alembic_cfg() -> Config:
    return Config("alembic.ini")


def baseline_if_needed() -> bool:
    """Stamp head when app tables exist but alembic_version does not.

    Returns True if a stamp was applied.
    """
    from app.db import engine

    insp = inspect(engine)
    tables = set(insp.get_table_names())
    if "alembic_version" in tables:
        return False
    if _EXISTING_SENTINEL not in tables:
        return False
    log.warning(
        "existing schema without alembic_version — stamping head "
        "(one-time baseline for pre-Alembic Railway DB)"
    )
    command.stamp(_alembic_cfg(), "head")
    return True


def upgrade_head() -> None:
    baseline_if_needed()
    command.upgrade(_alembic_cfg(), "head")
    log.info("alembic upgrade head complete")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO)
    argv = argv if argv is not None else sys.argv[1:]
    if argv and argv[0] in {"-h", "--help"}:
        print("usage: python -m app.migrate   # stamp-if-needed + upgrade head")
        return 0
    upgrade_head()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
