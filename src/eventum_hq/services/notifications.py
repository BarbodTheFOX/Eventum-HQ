"""Notification outbox.

Services never send Telegram messages. They call :func:`enqueue` inside their
transaction. Delivery is done by the bot layer (``bot/outbox.py``):

* M0: urgent rows are flushed right after each update is handled.
* M5: the 60-second tick delivers scheduled rows, applies quiet hours and retries.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from eventum_hq.core.db import Database
from eventum_hq.core.timeutil import Clock
from eventum_hq.models import Notification, NotificationStatus
from eventum_hq.repositories import notifications as repo

MAX_ATTEMPTS = 5
MAX_ERROR_LENGTH = 500


async def enqueue(
    session: AsyncSession,
    *,
    chat_id: int,
    kind: str,
    payload: dict[str, Any],
    dedupe_key: str,
    now: datetime,
    urgent: bool = False,
    scheduled_at: datetime | None = None,
) -> Notification | None:
    """Add an outbox row. Returns ``None`` if ``dedupe_key`` was already used."""
    if await repo.exists_dedupe_key(session, dedupe_key):
        return None
    row = Notification(
        chat_id=chat_id,
        kind=kind,
        payload=payload,
        dedupe_key=dedupe_key,
        urgent=urgent,
        scheduled_at=scheduled_at or now,
        attempts=0,
        status=NotificationStatus.PENDING,
    )
    session.add(row)
    await session.flush()
    return row


class OutboxStore:
    """Reads due rows and records delivery results."""

    def __init__(self, db: Database, clock: Clock) -> None:
        self._db = db
        self._clock = clock

    async def due_urgent(self, limit: int = 50) -> Sequence[Notification]:
        async with self._db.read() as session:
            return await repo.list_due(
                session, now=self._clock.now(), urgent_only=True, limit=limit
            )

    async def mark_sent(self, notification_id: int) -> None:
        async with self._db.transaction() as session:
            row = await session.get(Notification, notification_id)
            if row is None or row.status != NotificationStatus.PENDING:
                return
            row.status = NotificationStatus.SENT
            row.sent_at = self._clock.now()
            row.attempts += 1
            row.last_error = None

    async def mark_failed(self, notification_id: int, error: str, *, permanent: bool = False) -> None:
        async with self._db.transaction() as session:
            row = await session.get(Notification, notification_id)
            if row is None or row.status != NotificationStatus.PENDING:
                return
            row.attempts += 1
            row.last_error = error[:MAX_ERROR_LENGTH]
            if permanent or row.attempts >= MAX_ATTEMPTS:
                row.status = NotificationStatus.FAILED
