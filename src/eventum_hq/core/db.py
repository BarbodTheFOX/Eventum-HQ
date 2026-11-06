"""Async engine + session factory. Each service operation is one transaction."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


def sqlite_file_path(url: str) -> Path | None:
    """Return the file path of a SQLite URL, or ``None`` for memory / other DBs."""
    parsed = make_url(url)
    if not parsed.drivername.startswith("sqlite"):
        return None
    database = parsed.database
    if not database or database == ":memory:":
        return None
    return Path(database)


class Database:
    def __init__(self, url: str, *, echo: bool = False) -> None:
        self.url = url
        is_sqlite = make_url(url).drivername.startswith("sqlite")
        file_path = sqlite_file_path(url)
        is_memory = is_sqlite and file_path is None
        kwargs: dict[str, object] = {"echo": echo}
        if is_memory:
            # one shared connection so every session sees the same in-memory DB
            kwargs.update(poolclass=StaticPool, connect_args={"check_same_thread": False})
        elif file_path is not None:
            file_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_async_engine(url, **kwargs)

        if is_sqlite:

            @event.listens_for(self.engine.sync_engine, "connect")
            def _sqlite_pragmas(dbapi_conn, _record):  # type: ignore[no-untyped-def]
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA busy_timeout=5000")
                if not is_memory:
                    cursor.execute("PRAGMA journal_mode=WAL")
                cursor.close()

        self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncSession]:
        """Session inside one transaction: commit on success, rollback on error."""
        async with self.sessionmaker() as session, session.begin():
            yield session

    @asynccontextmanager
    async def read(self) -> AsyncIterator[AsyncSession]:
        async with self.sessionmaker() as session:
            yield session

    async def dispose(self) -> None:
        await self.engine.dispose()
