"""Audit log: every state change writes one ``AuditEvent`` in the same transaction."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from eventum_hq.models import AuditEvent


async def record(
    session: AsyncSession,
    *,
    actor_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int,
    at: datetime,
    data: dict[str, Any] | None = None,
) -> AuditEvent:
    """Add an audit event to the current transaction. ``actor_id=None`` = system."""
    event = AuditEvent(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        at=at,
        data=data or {},
    )
    session.add(event)
    await session.flush()
    return event
