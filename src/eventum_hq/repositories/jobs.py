"""``job_runs``: remembers which scheduled job ran for which key (idempotent tick)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eventum_hq.models import JobRun

HEARTBEAT_JOB = "tick"
HEARTBEAT_KEY = "last"


async def get(session: AsyncSession, job: str, run_key: str) -> JobRun | None:
    result = await session.execute(select(JobRun).where(JobRun.job == job, JobRun.run_key == run_key))
    return result.scalar_one_or_none()


async def claim(session: AsyncSession, job: str, run_key: str, now: datetime) -> bool:
    """Record a run. Returns False if this job already ran for ``run_key``."""
    if await get(session, job, run_key) is not None:
        return False
    session.add(JobRun(job=job, run_key=run_key, ran_at=now))
    await session.flush()
    return True


async def touch(session: AsyncSession, job: str, run_key: str, now: datetime) -> datetime | None:
    """Upsert ``ran_at`` and return the previous value (None on the first run)."""
    row = await get(session, job, run_key)
    if row is None:
        session.add(JobRun(job=job, run_key=run_key, ran_at=now))
        await session.flush()
        return None
    previous = row.ran_at
    row.ran_at = now
    return previous
