"""Data access for tasks and task inputs."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from eventum_hq.models import Task, TaskInput, TaskInputKind, TaskStatus
from eventum_hq.services.task_states import OPEN


async def get(session: AsyncSession, task_id: int) -> Task | None:
    return await session.get(Task, task_id)


async def get_by_code(session: AsyncSession, code: str) -> Task | None:
    result = await session.execute(select(Task).where(Task.code == code))
    return result.scalar_one_or_none()


def _open_query() -> Select[tuple[Task]]:
    return select(Task).where(Task.status.in_(OPEN))


def _ordered(query: Select[tuple[Task]]) -> Select[tuple[Task]]:
    # tasks without a deadline last, then by deadline, then oldest first
    return query.order_by(Task.due_at.is_(None), Task.due_at, Task.id)


async def list_open(
    session: AsyncSession,
    *,
    assignee_id: int | None = None,
    series_id: int | None = None,
    not_submitted: bool = False,
    due_before: datetime | None = None,
    due_from: datetime | None = None,
    exclude_blocked: bool = False,
) -> Sequence[Task]:
    query = _open_query()
    if exclude_blocked:
        query = query.where(Task.status != TaskStatus.BLOCKED)
    if assignee_id is not None:
        query = query.where(Task.assignee_id == assignee_id)
    if series_id is not None:
        query = query.where(Task.series_id == series_id)
    if not_submitted:
        query = query.where(Task.first_submitted_at.is_(None))
    if due_before is not None:
        query = query.where(Task.due_at.is_not(None), Task.due_at < due_before)
    if due_from is not None:
        query = query.where(Task.due_at.is_not(None), Task.due_at >= due_from)
    result = await session.execute(_ordered(query))
    return result.scalars().all()


async def latest_input(session: AsyncSession, task_id: int, kind: TaskInputKind) -> TaskInput | None:
    result = await session.execute(
        select(TaskInput)
        .where(TaskInput.task_id == task_id, TaskInput.kind == kind)
        .order_by(TaskInput.provided_at.desc(), TaskInput.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def inputs_of(session: AsyncSession, task_id: int) -> Sequence[TaskInput]:
    result = await session.execute(
        select(TaskInput).where(TaskInput.task_id == task_id).order_by(TaskInput.provided_at, TaskInput.id)
    )
    return result.scalars().all()
