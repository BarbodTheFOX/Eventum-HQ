"""Data access for users."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eventum_hq.models import AccessStatus, Role, User


async def get_by_id(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def get_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def list_active_owners(session: AsyncSession) -> Sequence[User]:
    result = await session.execute(
        select(User)
        .where(
            User.role == Role.OWNER,
            User.is_active.is_(True),
            User.access_status == AccessStatus.APPROVED,
        )
        .order_by(User.id)
    )
    return result.scalars().all()


async def list_active(session: AsyncSession) -> Sequence[User]:
    """Approved, active users — the people a task can be assigned to."""
    result = await session.execute(
        select(User)
        .where(User.is_active.is_(True), User.access_status == AccessStatus.APPROVED)
        .order_by(User.full_name, User.id)
    )
    return result.scalars().all()


async def get_many(session: AsyncSession, ids: set[int]) -> dict[int, User]:
    if not ids:
        return {}
    result = await session.execute(select(User).where(User.id.in_(ids)))
    return {u.id: u for u in result.scalars()}
