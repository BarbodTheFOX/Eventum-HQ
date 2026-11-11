"""Deadline reminders and overdue alerts (F11, handoff §5.4). Run by the tick.

* Reminder to the assignee at ``reminder_time`` (10:00) on the due day, and
  ``reminder_before_hours`` (2h) before the deadline.
* Overdue: one alert when the deadline passes — to the assignee and to everyone
  with a *stored* ``RECEIVE_OVERDUE_ALERTS`` — then a daily summary at 10:00.

Overdue means: not delivered yet (no first submission) and past due. Review
queue time never counts (§4.7) and a BLOCKED task is never overdue (§4.5), so
neither gets reminders or overdue alerts.

Everything is written to the outbox with a dedupe key that contains the
deadline, so a changed deadline re-arms the reminders.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eventum_hq.core.db import Database
from eventum_hq.core.timeutil import Clock
from eventum_hq.models import Capability, Task, TaskStatus, User
from eventum_hq.repositories import jobs as jobs_repo
from eventum_hq.repositories import users as users_repo
from eventum_hq.services import schedule
from eventum_hq.services.notifications import enqueue
from eventum_hq.services.permissions import stored_capabilities

KIND_REMINDER_DAY = "deadline.reminder_day"
KIND_REMINDER_SOON = "deadline.reminder_soon"
KIND_OVERDUE = "deadline.overdue"  # to the assignee
KIND_OVERDUE_WATCH = "deadline.overdue_watch"  # to RECEIVE_OVERDUE_ALERTS
KIND_OVERDUE_DAILY = "deadline.overdue_daily"

SCOPE_MINE = "mine"
SCOPE_ALL = "all"

ACTIVE_STATUSES = (TaskStatus.TODO, TaskStatus.IN_PROGRESS)
CROSSING_ALERT_WINDOW = timedelta(hours=24)  # older ones are only in the daily summary
SOON_WINDOW = timedelta(minutes=15)  # the "2h before" reminder only fires shortly after due-2h,
# so a task assigned 1h before its deadline does not get a reminder right after the assignment.


@dataclass(frozen=True, slots=True)
class OverdueRow:
    task: Task
    assignee: User


def _due_key(task: Task) -> str:
    return task.due_at.isoformat() if task.due_at else "none"


async def _pending_tasks(session: AsyncSession) -> Sequence[Task]:
    """Open, undelivered tasks with a deadline (candidates for reminders/overdue)."""
    result = await session.execute(
        select(Task)
        .where(
            Task.status.in_(ACTIVE_STATUSES),
            Task.first_submitted_at.is_(None),
            Task.due_at.is_not(None),
        )
        .order_by(Task.due_at, Task.id)
    )
    return result.scalars().all()


async def overdue_watchers(session: AsyncSession) -> list[User]:
    return [
        u for u in await users_repo.list_active(session)
        if Capability.RECEIVE_OVERDUE_ALERTS in stored_capabilities(u)
    ]


class DeadlineService:
    def __init__(self, db: Database, clock: Clock) -> None:
        self._db = db
        self._clock = clock

    async def run(self) -> int:
        """Queue every reminder/alert that is due now. Returns how many rows were queued."""
        now = self._clock.now()
        queued = 0
        async with self._db.transaction() as session:
            cfg = await schedule.load(session)
            tasks = await _pending_tasks(session)
            users = await users_repo.get_many(session, {t.assignee_id for t in tasks})
            watchers = await overdue_watchers(session)
            reminder_at = schedule.today_at(now, cfg.reminder_time)
            today = schedule.local_date_key(now)
            # once a day, at the first tick after 10:00: tasks due later today
            morning = now >= reminder_at and await jobs_repo.claim(session, "reminder.day", today, now)
            for task in tasks:
                assignee = users.get(task.assignee_id)
                if assignee is None or not assignee.can_use_bot:
                    continue
                due = task.due_at
                assert due is not None
                if due > now:
                    if morning and schedule.local_date_key(due) == today:
                        queued += await self._queue(session, KIND_REMINDER_DAY, assignee, task, now)
                    soon_from = due - cfg.reminder_before
                    if soon_from <= now < soon_from + SOON_WINDOW:
                        queued += await self._queue(session, KIND_REMINDER_SOON, assignee, task, now)
                    continue
                if now - due > CROSSING_ALERT_WINDOW:
                    continue
                queued += await self._queue(session, KIND_OVERDUE, assignee, task, now)
                for watcher in watchers:
                    if watcher.id != assignee.id:
                        queued += await self._queue(session, KIND_OVERDUE_WATCH, watcher, task, now,
                                                    assignee_name=assignee.full_name)
            if now >= reminder_at and await jobs_repo.claim(session, "overdue.daily", today, now):
                queued += await self._queue_daily(session, tasks, users, watchers, now)
        return queued

    async def overdue_for(self, viewer: User, scope: str) -> list[OverdueRow]:
        """Tasks overdue since before today (the daily summary's list) for ``viewer``."""
        now = self._clock.now()
        cutoff = schedule.start_of_today(now)
        async with self._db.read() as session:
            tasks = [t for t in await _pending_tasks(session) if t.due_at is not None and t.due_at < cutoff]
            if scope == SCOPE_MINE:
                tasks = [t for t in tasks if t.assignee_id == viewer.id]
            users = await users_repo.get_many(session, {t.assignee_id for t in tasks})
        return [OverdueRow(t, users[t.assignee_id]) for t in tasks if t.assignee_id in users]

    async def _queue_daily(
        self, session: AsyncSession, tasks: Sequence[Task], users: dict[int, User], watchers: list[User],
        now: datetime,
    ) -> int:
        cutoff = schedule.start_of_today(now)
        late = [t for t in tasks if t.due_at is not None and t.due_at < cutoff]
        if not late:
            return 0
        queued = 0
        day = schedule.local_date_key(now)
        for assignee_id in sorted({t.assignee_id for t in late}):
            user = users.get(assignee_id)
            if user is not None and user.can_use_bot:
                queued += await self._queue_summary(session, user, SCOPE_MINE, day, now)
        for watcher in watchers:
            queued += await self._queue_summary(session, watcher, SCOPE_ALL, day, now)
        return queued

    async def _queue_summary(self, session: AsyncSession, user: User, scope: str, day: str, now: datetime) -> int:
        row = await enqueue(
            session, chat_id=user.telegram_id, kind=KIND_OVERDUE_DAILY,
            payload={"user_id": user.id, "scope": scope},
            dedupe_key=f"{KIND_OVERDUE_DAILY}:{user.id}:{scope}:{day}", now=now,
        )
        return 0 if row is None else 1

    async def _queue(
        self, session: AsyncSession, kind: str, recipient: User, task: Task, now: datetime,
        *, assignee_name: str | None = None,
    ) -> int:
        payload = {"task_id": task.id, "user_id": recipient.id, "code": task.code, "title": task.title}
        if assignee_name is not None:
            payload["assignee"] = assignee_name
        row = await enqueue(
            session, chat_id=recipient.telegram_id, kind=kind, payload=payload,
            dedupe_key=f"{kind}:{task.id}:{recipient.id}:{_due_key(task)}", now=now,
        )
        return 0 if row is None else 1
