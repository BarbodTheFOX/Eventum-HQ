"""Notification outbox.

Services never send Telegram messages. They call :func:`enqueue` inside their
transaction. Delivery is done by the bot layer (``bot/outbox.py``):

* Urgent rows are flushed right after each update is handled.
* The 60-second tick (M5) delivers every due row.
* Quiet hours (23:00–09:00 Tehran): nothing goes out; rows wait and are sent when
  the window ends. Only a review request to the OWNER may pass, if the setting
  ``owner_review_urgent_in_quiet_hours`` is on (off by default).
* A failed send is retried with backoff (1, 2, 4, 8 minutes), at most 5 attempts.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from eventum_hq.core.db import Database
from eventum_hq.core.timeutil import Clock
from eventum_hq.models import Notification, NotificationStatus
from eventum_hq.repositories import notifications as repo
from eventum_hq.repositories import users as users_repo
from eventum_hq.services import schedule

MAX_ATTEMPTS = 5
MAX_ERROR_LENGTH = 500
MAX_BACKOFF = timedelta(minutes=30)
KIND_REVIEW_REQUESTED = "review.requested"  # same string as services.reviews (no import cycle)


def backoff(attempts: int) -> timedelta:
    """Wait before the next try after ``attempts`` failures: 1, 2, 4, 8 … minutes."""
    return min(timedelta(minutes=2 ** max(attempts - 1, 0)), MAX_BACKOFF)


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
        return await self._due(urgent_only=True, limit=limit)

    async def due_all(self, limit: int = 100) -> Sequence[Notification]:
        return await self._due(urgent_only=False, limit=limit)

    async def in_quiet_hours(self) -> bool:
        async with self._db.read() as session:
            cfg = await schedule.load(session)
        return schedule.in_quiet_hours(self._clock.now(), cfg.quiet_start, cfg.quiet_end)

    async def _due(self, *, urgent_only: bool, limit: int) -> Sequence[Notification]:
        now = self._clock.now()
        async with self._db.read() as session:
            rows = await repo.list_due(session, now=now, urgent_only=urgent_only, limit=limit)
            cfg = await schedule.load(session)
            if not schedule.in_quiet_hours(now, cfg.quiet_start, cfg.quiet_end):
                return rows
            if not cfg.owner_review_urgent_in_quiet:
                return []
            owners = {u.telegram_id for u in await users_repo.list_active_owners(session)}
            return [r for r in rows if r.kind == KIND_REVIEW_REQUESTED and r.chat_id in owners]

    async def mark_sent(self, notification_id: int) -> None:
        async with self._db.transaction() as session:
            row = await session.get(Notification, notification_id)
            if row is None or row.status != NotificationStatus.PENDING:
                return
            row.status = NotificationStatus.SENT
            row.sent_at = self._clock.now()
            row.attempts += 1
            row.last_error = None

    async def mark_failed(
        self, notification_id: int, error: str, *, permanent: bool = False, retry_after: float | None = None
    ) -> None:
        async with self._db.transaction() as session:
            row = await session.get(Notification, notification_id)
            if row is None or row.status != NotificationStatus.PENDING:
                return
            row.attempts += 1
            row.last_error = error[:MAX_ERROR_LENGTH]
            if permanent or row.attempts >= MAX_ATTEMPTS:
                row.status = NotificationStatus.FAILED
                return
            wait = backoff(row.attempts)
            if retry_after is not None:
                wait = max(wait, timedelta(seconds=retry_after))
            row.scheduled_at = self._clock.now() + wait

    async def pending_count(self) -> int:
        async with self._db.read() as session:
            return await repo.count_pending(session)
