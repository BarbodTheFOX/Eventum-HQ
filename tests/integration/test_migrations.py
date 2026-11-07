"""The first migration creates the schema and seeds series + settings (handoff §7)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command

from eventum_hq.core.migrate import alembic_config, upgrade_to_head
from eventum_hq.models import Base


def _url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path.as_posix()}"


def test_upgrade_creates_tables_and_seed(tmp_path: Path) -> None:
    db_file = tmp_path / "data" / "eventum.db"  # parent dir does not exist yet
    upgrade_to_head(_url(db_file))

    con = sqlite3.connect(db_file)
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert set(Base.metadata.tables) <= tables

        series = [r[0] for r in con.execute("SELECT name FROM series ORDER BY id")]
        assert series == [
            "ریل روزانه", "Trial Reels", "PURPLE ZONE", "سری WEEX", "دوئل تریدرها", "ERANTE",
        ]

        settings = dict(con.execute("SELECT key, value FROM settings"))
        assert settings["timezone"] == '"Asia/Tehran"'
        assert '"23:00"' in settings["quiet_hours"]
        assert settings["revision_returns_to_requesting_stage"] == "true"
        assert settings["owner_review_urgent_in_quiet_hours"] == "false"
        assert len(settings) == 11

        mode = con.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"
    finally:
        con.close()


def test_upgrade_is_idempotent_and_downgrade_works(tmp_path: Path) -> None:
    url = _url(tmp_path / "eventum.db")
    upgrade_to_head(url)
    upgrade_to_head(url)  # second run is a no-op (bot restarts)
    command.downgrade(alembic_config(url), "base")
    con = sqlite3.connect(tmp_path / "eventum.db")
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert tables <= {"alembic_version"}
    finally:
        con.close()


def test_models_match_migrations(tmp_path: Path) -> None:
    """Fails if someone changes a model without writing a migration."""
    import asyncio

    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from sqlalchemy.ext.asyncio import create_async_engine

    url = _url(tmp_path / "eventum.db")
    upgrade_to_head(url)

    async def diff() -> list:
        engine = create_async_engine(url)
        async with engine.connect() as conn:
            result = await conn.run_sync(
                lambda c: compare_metadata(MigrationContext.configure(c), Base.metadata)
            )
        await engine.dispose()
        return result

    assert asyncio.run(diff()) == []


def test_0002_remaps_old_roles(tmp_path: Path) -> None:
    db_file = tmp_path / "eventum.db"
    url = _url(db_file)
    command.upgrade(alembic_config(url), "0001")
    con = sqlite3.connect(db_file)
    now = "2026-11-07 00:00:00.000000"
    rows = [
        (1, "OWNER", "[]"),
        (2, "MANAGER", '["CREATE_TASK"]'),
        (3, "MEMBER", '["PUBLISH"]'),
    ]
    con.executemany(
        "INSERT INTO users (telegram_id, full_name, role, capabilities, is_active, "
        "access_status, created_at, updated_at) VALUES (?, 'x', ?, ?, 1, 'APPROVED', ?, ?)",
        [(tg, role, caps, now, now) for tg, role, caps in rows],
    )
    con.commit()
    con.close()

    upgrade_to_head(url)
    con = sqlite3.connect(db_file)
    try:
        got = dict(con.execute("SELECT telegram_id, role FROM users"))
        assert got == {1: "OWNER", 2: "PROJECT_MANAGER", 3: "EDITOR"}
        caps = dict(con.execute("SELECT telegram_id, capabilities FROM users"))
        assert caps[1] == '["PUBLISH", "SYSTEM_ADMIN"]'
        assert caps[2] == '["CREATE_TASK"]'  # untouched
    finally:
        con.close()
