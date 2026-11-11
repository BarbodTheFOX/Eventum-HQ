"""Database backups (F16, handoff §6.5).

* Daily: an online copy with SQLite's backup API to ``data/backups/eventum-YYYYMMDD.db``;
  the newest ``KEEP`` copies are kept.
* Weekly: the newest copy is gzipped so the bot can send it to SYSTEM_ADMINs.
  Above ``MAX_SEND_BYTES`` it is only kept locally (Telegram bots cannot send >50MB).

Files (videos, photos) live only in the Telegram archive channel; the database
holds their ``file_id`` references. That limit is accepted for v0.
"""

from __future__ import annotations

import asyncio
import gzip
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

KEEP = 14
MAX_SEND_BYTES = 45 * 1024 * 1024
PREFIX = "eventum-"


@dataclass(frozen=True, slots=True)
class WeeklyBackup:
    path: Path
    size: int
    sendable: bool


def backup_name(day: date) -> str:
    return f"{PREFIX}{day:%Y%m%d}.db"


def _copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    src = sqlite3.connect(str(source))
    try:
        dst = sqlite3.connect(str(tmp))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    tmp.replace(target)


def _prune(folder: Path, keep: int) -> list[Path]:
    copies = sorted(folder.glob(f"{PREFIX}*.db"))
    removed = copies[:-keep] if len(copies) > keep else []
    for path in removed:
        path.unlink(missing_ok=True)
    return removed


def _gzip(source: Path) -> Path:
    target = source.with_suffix(".db.gz")
    with source.open("rb") as raw, gzip.open(target, "wb") as packed:
        shutil.copyfileobj(raw, packed)
    return target


class BackupService:
    def __init__(self, database_file: Path | None, folder: Path) -> None:
        self._source = database_file
        self._folder = folder

    @property
    def enabled(self) -> bool:
        return self._source is not None

    async def daily(self, day: date) -> Path | None:
        """Copy the database for ``day`` and drop old copies. None if there is no DB file."""
        if self._source is None:
            return None
        target = self._folder / backup_name(day)
        await asyncio.to_thread(_copy, self._source, target)
        await asyncio.to_thread(_prune, self._folder, KEEP)
        return target

    async def weekly(self, day: date) -> WeeklyBackup | None:
        """Gzip the newest copy (making one for ``day`` if needed)."""
        if self._source is None:
            return None
        copies = sorted(self._folder.glob(f"{PREFIX}*.db"))
        latest = copies[-1] if copies else await self.daily(day)
        if latest is None:
            return None
        packed = await asyncio.to_thread(_gzip, latest)
        size = packed.stat().st_size
        return WeeklyBackup(packed, size, size <= MAX_SEND_BYTES)
