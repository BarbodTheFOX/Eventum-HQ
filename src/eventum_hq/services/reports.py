"""Report data (handoff §5.5, §5.6, F17). Pure numbers; the bot layer formats them.

* :meth:`ReportService.saturday` — the private Saturday report (also «📊 گزارش»).
* :meth:`ReportService.daily_plan` — «برنامهٔ امروز» for the team group: today's
  deliveries per person and today's planned publishes. Never delays, revisions
  or per-person performance.
* :meth:`ReportService.weekly_summary` — Thursday group message: this week's
  approved outputs and publishes by type (not by person), next week's publishes.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eventum_hq.core.db import Database
from eventum_hq.core.errors import PermissionDenied
from eventum_hq.core.jalali import tehran_to_utc, tehran_today
from eventum_hq.core.timeutil import Clock
from eventum_hq.models import (
    Capability,
    ContentItem,
    ContentStatus,
    Output,
    ReviewStage,
    Task,
    TaskStatus,
    User,
)
from eventum_hq.repositories import reviews as reviews_repo
from eventum_hq.repositories import users as users_repo
from eventum_hq.services import schedule
from eventum_hq.services.permissions import has_capability, is_owner, stored_capabilities
from eventum_hq.services.task_states import is_open
from eventum_hq.services.tasks import DeadlineState, deadline_state

WEEK = timedelta(days=7)


@dataclass(frozen=True, slots=True)
class TaskLine:
    task: Task
    assignee: User
    state: DeadlineState


@dataclass(frozen=True, slots=True)
class PublishLine:
    item: ContentItem
    open_tasks: list[Task]  # what is still missing (empty = ready)


@dataclass(frozen=True, slots=True)
class PersonLoad:
    user: User
    open_count: int
    open_minutes: int
    week_count: int
    week_minutes: int
    over_capacity: bool
    without_estimate: int
    on_time_percent: int | None  # None = nothing delivered in the last 7 days
    avg_revisions: float | None  # None = nothing finished in the last 7 days


@dataclass(frozen=True, slots=True)
class SaturdayReport:
    approvals: list[TaskLine]
    overdue: list[TaskLine]
    at_risk: list[TaskLine]
    publishes: list[PublishLine]
    people: list[PersonLoad]


@dataclass(frozen=True, slots=True)
class DailyPlan:
    day: date
    deliveries: list[tuple[User, list[Task]]]
    publishes: list[ContentItem]

    @property
    def empty(self) -> bool:
        return not self.deliveries and not self.publishes


@dataclass(frozen=True, slots=True)
class WeeklySummary:
    outputs_by_type: dict[str, int]
    published_reels: int
    next_week: list[ContentItem] = field(default_factory=list)


def can_receive_report(user: User) -> bool:
    return is_owner(user) or Capability.RECEIVE_WEEKLY_REPORT in stored_capabilities(user)


def _delivered_at(task: Task) -> datetime | None:
    return task.first_submitted_at or (task.completed_at if task.status == TaskStatus.DONE else None)


class ReportService:
    def __init__(self, db: Database, clock: Clock) -> None:
        self._db = db
        self._clock = clock

    async def saturday(self, viewer: User) -> SaturdayReport:
        now = self._clock.now()
        async with self._db.read() as session:
            fresh = await users_repo.get_by_id(session, viewer.id)
            if fresh is None or not fresh.can_use_bot or not has_capability(fresh, Capability.RECEIVE_WEEKLY_REPORT):
                raise PermissionDenied("report")
            tasks = list((await session.execute(select(Task).order_by(Task.due_at, Task.id))).scalars())
            people = {u.id: u for u in await users_repo.list_active(session)}
            approvals: list[TaskLine] = []
            if is_owner(fresh) or Capability.APPROVE_FINAL in stored_capabilities(fresh):
                for t in await reviews_repo.tasks_in_review(session, ReviewStage.FINAL):
                    if t.assignee_id in people:
                        approvals.append(TaskLine(t, people[t.assignee_id], DeadlineState.NONE))
            publishes = await self._publishes(session, tasks, now, now + WEEK)

        overdue: list[TaskLine] = []
        at_risk: list[TaskLine] = []
        for t in tasks:
            state = deadline_state(t, now)
            if t.assignee_id not in people:
                continue
            if state == DeadlineState.OVERDUE:
                overdue.append(TaskLine(t, people[t.assignee_id], state))
            elif state == DeadlineState.AT_RISK:
                at_risk.append(TaskLine(t, people[t.assignee_id], state))
        return SaturdayReport(approvals, overdue, at_risk, publishes, self._loads(tasks, people, now))

    async def daily_plan(self) -> DailyPlan:
        now = self._clock.now()
        today = tehran_today(now)
        start, end = tehran_to_utc(today, schedule.parse_hhmm("00:00")), tehran_to_utc(
            today + timedelta(days=1), schedule.parse_hhmm("00:00"))
        async with self._db.read() as session:
            result = await session.execute(
                select(Task).where(Task.due_at >= start, Task.due_at < end,
                                   Task.status != TaskStatus.CANCELLED).order_by(Task.due_at, Task.id)
            )
            tasks = list(result.scalars())
            users = await users_repo.get_many(session, {t.assignee_id for t in tasks})
            items = await self._planned(session, start, end)
        by_user: dict[int, list[Task]] = {}
        for t in tasks:
            by_user.setdefault(t.assignee_id, []).append(t)
        deliveries = [(users[uid], ts) for uid, ts in by_user.items() if uid in users]
        return DailyPlan(today, deliveries, items)

    async def weekly_summary(self) -> WeeklySummary:
        now = self._clock.now()
        week_start = schedule.week_start(now)
        start = tehran_to_utc(week_start, schedule.parse_hhmm("00:00"))
        next_start = tehran_to_utc(week_start + WEEK, schedule.parse_hhmm("00:00"))
        next_end = tehran_to_utc(week_start + 2 * WEEK, schedule.parse_hhmm("00:00"))
        async with self._db.read() as session:
            outputs = (await session.execute(
                select(Output).where(Output.approved_at >= start, Output.approved_at <= now))).scalars()
            by_type = Counter(str(o.output_type) for o in outputs)
            published = (await session.execute(
                select(ContentItem).where(ContentItem.published_at >= start,
                                          ContentItem.published_at <= now))).scalars().all()
            upcoming = await self._planned(session, next_start, next_end)
        return WeeklySummary(dict(by_type), len(published), upcoming)

    # ---- helpers --------------------------------------------------------------

    async def _planned(self, session: AsyncSession, start: datetime, end: datetime) -> list[ContentItem]:
        result = await session.execute(
            select(ContentItem).where(
                ContentItem.planned_publish_at >= start, ContentItem.planned_publish_at < end,
                ContentItem.status.in_((ContentStatus.IN_PRODUCTION, ContentStatus.READY_TO_PUBLISH)),
            ).order_by(ContentItem.planned_publish_at, ContentItem.id)
        )
        return list(result.scalars())

    async def _publishes(
        self, session: AsyncSession, tasks: list[Task], start: datetime, end: datetime
    ) -> list[PublishLine]:
        items = await self._planned(session, start, end)
        return [
            PublishLine(item, [t for t in tasks if t.content_item_id == item.id and is_open(t.status)])
            for item in items
        ]

    def _loads(self, tasks: list[Task], people: dict[int, User], now: datetime) -> list[PersonLoad]:
        week_start = tehran_to_utc(schedule.week_start(now), schedule.parse_hhmm("00:00"))
        week_end = week_start + WEEK
        since = now - WEEK
        loads: list[PersonLoad] = []
        for user in people.values():
            mine = [t for t in tasks if t.assignee_id == user.id]
            open_tasks = [t for t in mine if is_open(t.status)]
            week = [t for t in mine if t.status != TaskStatus.CANCELLED and t.due_at is not None
                    and week_start <= t.due_at < week_end]
            if not open_tasks and not week:
                continue
            week_minutes = sum(t.estimated_minutes or 0 for t in week)
            capacity = user.weekly_capacity_hours
            delivered = [t for t in mine if (d := _delivered_at(t)) is not None and d >= since
                         and t.due_at is not None]
            on_time = (round(100 * sum(1 for t in delivered if _delivered_at(t) <= t.due_at) / len(delivered))
                       if delivered else None)
            finished = [t for t in mine if t.completed_at is not None and t.completed_at >= since]
            avg_rev = (sum(t.revision_round for t in finished) / len(finished)) if finished else None
            loads.append(PersonLoad(
                user=user,
                open_count=len(open_tasks),
                open_minutes=sum(t.estimated_minutes or 0 for t in open_tasks),
                week_count=len(week),
                week_minutes=week_minutes,
                over_capacity=capacity is not None and week_minutes > capacity * 60,
                without_estimate=sum(1 for t in open_tasks if t.estimated_minutes is None),
                on_time_percent=on_time,
                avg_revisions=avg_rev,
            ))
        loads.sort(key=lambda p: p.user.id)
        return loads
