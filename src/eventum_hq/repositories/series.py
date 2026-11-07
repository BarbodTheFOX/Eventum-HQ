"""Data access for series."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eventum_hq.models import Series


async def list_active(session: AsyncSession) -> Sequence[Series]:
    result = await session.execute(
        select(Series).where(Series.is_active.is_(True)).order_by(Series.id)
    )
    return result.scalars().all()


async def get(session: AsyncSession, series_id: int) -> Series | None:
    return await session.get(Series, series_id)
