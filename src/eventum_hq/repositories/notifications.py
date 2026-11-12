"""Data access for the notification outbox."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from eventum_hq.models import Notification, NotificationStatus


async def exists_dedupe_key(session: AsyncSession, dedupe_key: str) -> bool:
    result = await session.execute(
        select(Notification.id).where(Notification.dedupe_key == dedupe_key).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def list_due(
    session: AsyncSession, *, now: datetime, urgent_only: bool, limit: int
) -> Sequence[Notification]:
    query = select(Notification).where(
        Notification.status == NotificationStatus.PENDING,
        Notification.scheduled_at <= now,
    )
    if urgent_only:
        query = query.where(Notification.urgent.is_(True))
    result = await session.execute(
        query.order_by(Notification.scheduled_at, Notification.id).limit(limit)
    )
    return result.scalars().all()


async def count_pending(session: AsyncSession) -> int:
    result = await session.execute(
        select(func.count(Notification.id)).where(Notification.status == NotificationStatus.PENDING)
    )
    return int(result.scalar_one())


async def cancel_pending_for_chat(session: AsyncSession, chat_id: int) -> int:
    """Cancel every pending row for one chat (e.g. a user who was just deactivated)."""
    result = await session.execute(
        select(Notification).where(
            Notification.chat_id == chat_id, Notification.status == NotificationStatus.PENDING
        )
    )
    rows = list(result.scalars().all())
    for row in rows:
        row.status = NotificationStatus.CANCELLED
    return len(rows)


async def count_failed_since(session: AsyncSession, since: datetime) -> int:
    result = await session.execute(
        select(func.count(Notification.id)).where(
            Notification.status == NotificationStatus.FAILED, Notification.updated_at >= since
        )
    )
    return int(result.scalar_one())