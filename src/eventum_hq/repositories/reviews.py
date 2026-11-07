"""Data access for submissions, reviews, outputs, delegations and settings."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from eventum_hq.models import (
    Delegation,
    Output,
    Review,
    ReviewStage,
    Setting,
    Submission,
    Task,
    TaskStatus,
)

# ---- submissions ---------------------------------------------------------------


async def max_version(session: AsyncSession, task_id: int) -> int:
    result = await session.execute(
        select(func.coalesce(func.max(Submission.version), 0)).where(Submission.task_id == task_id)
    )
    return int(result.scalar_one())


async def latest_submission(session: AsyncSession, task_id: int) -> Submission | None:
    result = await session.execute(
        select(Submission)
        .where(Submission.task_id == task_id)
        .order_by(Submission.version.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_submission(session: AsyncSession, submission_id: int) -> Submission | None:
    return await session.get(Submission, submission_id)


# ---- reviews -------------------------------------------------------------------


async def latest_review(session: AsyncSession, task_id: int) -> Review | None:
    result = await session.execute(
        select(Review)
        .join(Submission, Submission.id == Review.submission_id)
        .where(Submission.task_id == task_id)
        .order_by(Review.decided_at.desc(), Review.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_review(session: AsyncSession, review_id: int) -> Review | None:
    return await session.get(Review, review_id)


async def tasks_in_review(session: AsyncSession, stage: ReviewStage) -> Sequence[Task]:
    result = await session.execute(
        select(Task)
        .where(Task.status == TaskStatus.IN_REVIEW, Task.review_stage == stage)
        .order_by(Task.first_submitted_at, Task.id)
    )
    return result.scalars().all()


# ---- outputs -------------------------------------------------------------------


async def output_for_task(session: AsyncSession, task_id: int) -> Output | None:
    result = await session.execute(select(Output).where(Output.task_id == task_id))
    return result.scalar_one_or_none()


# ---- delegations ---------------------------------------------------------------


async def active_delegation(session: AsyncSession, now: datetime) -> Delegation | None:
    """The delegation in force right now (newest first if several overlap)."""
    result = await session.execute(
        select(Delegation)
        .where(
            Delegation.revoked_at.is_(None),
            Delegation.starts_at <= now,
            Delegation.ends_at > now,
        )
        .order_by(Delegation.starts_at.desc(), Delegation.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_delegation(session: AsyncSession, delegation_id: int) -> Delegation | None:
    return await session.get(Delegation, delegation_id)


# ---- settings ------------------------------------------------------------------


async def setting(session: AsyncSession, key: str, default: Any = None) -> Any:
    from eventum_hq.repositories.content import setting as _setting

    return await _setting(session, key, default)
