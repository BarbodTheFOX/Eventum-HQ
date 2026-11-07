"""Data access for audit events."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eventum_hq.models import AuditEvent


async def last_event(
    session: AsyncSession, *, entity_type: str, entity_id: int, action: str
) -> AuditEvent | None:
    result = await session.execute(
        select(AuditEvent)
        .where(
            AuditEvent.entity_type == entity_type,
            AuditEvent.entity_id == entity_id,
            AuditEvent.action == action,
        )
        .order_by(AuditEvent.at.desc(), AuditEvent.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def list_for_entity(
    session: AsyncSession, *, entity_type: str, entity_id: int
) -> Sequence[AuditEvent]:
    result = await session.execute(
        select(AuditEvent)
        .where(AuditEvent.entity_type == entity_type, AuditEvent.entity_id == entity_id)
        .order_by(AuditEvent.at, AuditEvent.id)
    )
    return result.scalars().all()


async def last_for_entity(
    session: AsyncSession, *, entity_type: str, entity_id: int
) -> AuditEvent | None:
    result = await session.execute(
        select(AuditEvent)
        .where(AuditEvent.entity_type == entity_type, AuditEvent.entity_id == entity_id)
        .order_by(AuditEvent.at.desc(), AuditEvent.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
