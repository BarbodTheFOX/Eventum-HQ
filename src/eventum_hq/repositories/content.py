"""Data access for content items (reels) and settings."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eventum_hq.models import ContentItem, ContentStatus, Output, Series, Setting, Task, TaskKind


async def setting(session: AsyncSession, key: str, default: Any = None) -> Any:
    row = await session.get(Setting, key)
    return default if row is None else row.value


async def get_item(session: AsyncSession, item_id: int) -> ContentItem | None:
    return await session.get(ContentItem, item_id)


async def get_item_by_code(session: AsyncSession, code: str) -> ContentItem | None:
    result = await session.execute(select(ContentItem).where(ContentItem.code == code))
    return result.scalar_one_or_none()


async def tasks_of(session: AsyncSession, item_id: int) -> Sequence[Task]:
    result = await session.execute(
        select(Task).where(Task.content_item_id == item_id).order_by(Task.id)
    )
    return result.scalars().all()


async def task_of_kind(session: AsyncSession, item_id: int, kind: TaskKind) -> Task | None:
    result = await session.execute(
        select(Task)
        .where(Task.content_item_id == item_id, Task.kind == kind)
        .order_by(Task.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def items_with_status(session: AsyncSession, status: ContentStatus) -> Sequence[ContentItem]:
    result = await session.execute(
        select(ContentItem)
        .where(ContentItem.status == status)
        .order_by(ContentItem.planned_publish_at.is_(None), ContentItem.planned_publish_at, ContentItem.id)
    )
    return result.scalars().all()


async def series_by_name(session: AsyncSession, name: str) -> Series | None:
    result = await session.execute(select(Series).where(Series.name == name))
    return result.scalar_one_or_none()


async def outputs_of(session: AsyncSession, item_id: int) -> Sequence[Output]:
    result = await session.execute(
        select(Output).where(Output.content_item_id == item_id).order_by(Output.id)
    )
    return result.scalars().all()
