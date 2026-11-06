"""Run Alembic migrations programmatically (``alembic upgrade head`` on startup)."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def find_alembic_ini() -> Path:
    for candidate in (Path.cwd() / "alembic.ini", _PROJECT_ROOT / "alembic.ini"):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "alembic.ini not found. Run the bot from the project folder (where alembic.ini is)."
    )


def alembic_config(database_url: str) -> Config:
    ini = find_alembic_ini()
    cfg = Config(str(ini))
    cfg.set_main_option("script_location", str(ini.parent / "migrations"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    cfg.attributes["configure_logger"] = False  # keep our logging setup
    return cfg


def upgrade_to_head(database_url: str) -> None:
    """Must be called outside a running event loop (env.py uses asyncio.run)."""
    command.upgrade(alembic_config(database_url), "head")
