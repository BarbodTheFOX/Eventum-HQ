"""Repeating generic tasks (F10, handoff §4.10).

A Recurrence is a template plus a rule (every day, or listed weekdays with
Saturday = 0). The tick calls :meth:`RecurrenceService.generate_due`; once
today's ``create_time`` has passed, today's task is created (once — the
``(recurrence_id, recurrence_date)`` pair is unique) and the assignee is told.
Turning a recurrence off or changing it never touches tasks already created.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eventum_hq.core.db import Database
from eventum_hq.core.errors import NotFound, PermissionDenied, ValidationFailed
from eventum_hq.core.jalali import ESTIMATE_MAX_MINUTES, tehran_to_utc, tehran_today
from eventum_hq.core.timeutil import Clock, weekday_sat0
from eventum_hq.integrations.sync import NoopSync, TaskSyncPort
from eventum_hq.models import (
    ApprovalChain,
    Capability,
    Recurrence,
    RecurrenceRule,
    Task,
    TaskKind,
    TaskStatus,
    User,
)
from eventum_hq.repositories import series as series_repo
from eventum_hq.repositories import users as users_repo
from eventum_hq.services import audit
from eventum_hq.services.notifications import enqueue
from eventum_hq.services.permissions import require_capability
from eventum_hq.services.tasks import KIND_TASK_ASSIGNED, TITLE_MAX

log = logging.getLogger(__name__)

ENTITY = "recurrence"
DEFAULT_CREATE_TIME = time(8, 30)
DEFAULT_DUE_TIME = time(18, 0)


@dataclass(slots=True)
class NewRecurrence:
    title: str
    assignee_id: int
    rule: RecurrenceRule
    weekdays: list[int] = field(default_factory=list)  # 0 = Saturday … 6 = Friday
    create_time: time = DEFAULT_CREATE_TIME
    due_time: time = DEFAULT_DUE_TIME
    approval_chain: ApprovalChain = ApprovalChain.FINAL
    estimated_minutes: int | None = None
    series_id: int | None = None
    description: str | None = None


@dataclass(frozen=True, slots=True)
class RecurrenceRow:
    recurrence: Recurrence
    assignee: User


def runs_on(recurrence: Recurrence, day_sat0: int) -> bool:
    if recurrence.rule == RecurrenceRule.DAILY:
        return True
    return day_sat0 in set(recurrence.weekdays or [])


class RecurrenceService:
    def __init__(self, db: Database, clock: Clock, sync: TaskSyncPort | None = None) -> None:
        self._db = db
        self._clock = clock
        self._sync = sync or NoopSync()

    # ---- manage ---------------------------------------------------------------

    async def create(self, actor: User, data: NewRecurrence) -> Recurrence:
        now = self._clock.now()
        title = (data.title or "").strip()
        if not title:
            raise ValidationFailed("title_empty")
        if len(title) > TITLE_MAX:
            raise ValidationFailed("title_too_long")
        rule = RecurrenceRule(data.rule)
        weekdays = sorted({int(d) for d in data.weekdays}) if rule == RecurrenceRule.WEEKDAYS else []
        if rule == RecurrenceRule.WEEKDAYS and (not weekdays or any(d < 0 or d > 6 for d in weekdays)):
            raise ValidationFailed("weekdays_invalid")
        if data.due_time <= data.create_time:
            raise ValidationFailed("due_before_create")
        estimate = data.estimated_minutes
        if estimate is not None and not (0 < estimate <= ESTIMATE_MAX_MINUTES):
            raise ValidationFailed("estimate_invalid")

        async with self._db.transaction() as session:
            fresh = await self._fresh_actor(session, actor)
            require_capability(fresh, Capability.CREATE_TASK)
            assignee = await users_repo.get_by_id(session, data.assignee_id)
            if assignee is None or not assignee.can_use_bot:
                raise ValidationFailed("assignee_invalid")
            if data.series_id is not None:
                series = await series_repo.get(session, data.series_id)
                if series is None or not series.is_active:
                    raise ValidationFailed("series_invalid")
            recurrence = Recurrence(
                title=title,
                description=(data.description or "").strip() or None,
                assignee_id=assignee.id,
                series_id=data.series_id,
                approval_chain=(ApprovalChain.FINAL if data.approval_chain == ApprovalChain.NONE
                                else ApprovalChain(data.approval_chain)),
                rule=rule,
                weekdays=weekdays,
                create_time=data.create_time,
                due_time=data.due_time,
                estimated_minutes=estimate,
                is_active=True,
                created_by=fresh.id,
            )
            session.add(recurrence)
            await session.flush()
            await audit.record(
                session, actor_id=fresh.id, action="recurrence.created", entity_type=ENTITY,
                entity_id=recurrence.id, at=now,
                data={"title": title, "assignee_id": assignee.id, "rule": str(rule), "weekdays": weekdays,
                      "create_time": data.create_time.isoformat(), "due_time": data.due_time.isoformat(),
                      "approval_chain": str(recurrence.approval_chain), "estimated_minutes": estimate},
            )
        return recurrence

    async def deactivate(self, actor: User, recurrence_id: int) -> Recurrence:
        now = self._clock.now()
        async with self._db.transaction() as session:
            fresh = await self._fresh_actor(session, actor)
            require_capability(fresh, Capability.CREATE_TASK)
            recurrence = await session.get(Recurrence, recurrence_id)
            if recurrence is None:
                raise NotFound("recurrence")
            if recurrence.is_active:
                recurrence.is_active = False
                await audit.record(session, actor_id=fresh.id, action="recurrence.deactivated",
                                   entity_type=ENTITY, entity_id=recurrence.id, at=now, data={})
        return recurrence

    async def list_active(self, actor: User) -> list[RecurrenceRow]:
        async with self._db.read() as session:
            fresh = await self._fresh_actor(session, actor)
            require_capability(fresh, Capability.CREATE_TASK)
            result = await session.execute(
                select(Recurrence).where(Recurrence.is_active.is_(True)).order_by(Recurrence.id)
            )
            rows = list(result.scalars())
            users = await users_repo.get_many(session, {r.assignee_id for r in rows})
        return [RecurrenceRow(r, users[r.assignee_id]) for r in rows if r.assignee_id in users]

    # ---- tick -----------------------------------------------------------------

    async def generate_due(self) -> list[Task]:
        """Create today's task for every active recurrence whose create time has passed."""
        now = self._clock.now()
        today = tehran_today(now)
        weekday = weekday_sat0(now)
        created: list[Task] = []
        async with self._db.transaction() as session:
            result = await session.execute(select(Recurrence).where(Recurrence.is_active.is_(True)))
            for recurrence in result.scalars():
                if not runs_on(recurrence, weekday) or now < tehran_to_utc(today, recurrence.create_time):
                    continue
                if await self._exists(session, recurrence.id, today):
                    continue
                assignee = await users_repo.get_by_id(session, recurrence.assignee_id)
                if assignee is None or not assignee.can_use_bot:
                    log.warning("recurrence %s skipped: assignee %s is inactive", recurrence.id,
                                recurrence.assignee_id)
                    continue
                created.append(await self._create_task(session, recurrence, assignee, today, now))
        for task in created:
            await self._sync.on_task_created(task.id)
        return created

    async def _exists(self, session: AsyncSession, recurrence_id: int, day: date) -> bool:
        result = await session.execute(
            select(Task.id).where(Task.recurrence_id == recurrence_id, Task.recurrence_date == day).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _create_task(
        self, session: AsyncSession, recurrence: Recurrence, assignee: User, day: date, now: datetime
    ) -> Task:
        task = Task(
            code=f"tmp-{uuid.uuid4().hex[:10]}",
            kind=TaskKind.GENERIC,
            title=recurrence.title,
            description=recurrence.description,
            series_id=recurrence.series_id,
            assignee_id=assignee.id,
            created_by=recurrence.created_by,
            status=TaskStatus.TODO,
            approval_chain=(ApprovalChain.FINAL if recurrence.approval_chain == ApprovalChain.NONE
                            else recurrence.approval_chain),
            due_at=tehran_to_utc(day, recurrence.due_time),
            estimated_minutes=recurrence.estimated_minutes,
            revision_round=0,
            recurrence_id=recurrence.id,
            recurrence_date=day,
        )
        session.add(task)
        await session.flush()
        task.code = f"T-{task.id:04d}"
        await audit.record(
            session, actor_id=None, action="task.created", entity_type="task", entity_id=task.id, at=now,
            data={"code": task.code, "title": task.title, "assignee_id": assignee.id,
                  "due_at": task.due_at.isoformat() if task.due_at else None,
                  "recurrence_id": recurrence.id, "approval_chain": str(task.approval_chain),
                  "estimated_minutes": task.estimated_minutes},
        )
        await enqueue(
            session, chat_id=assignee.telegram_id, kind=KIND_TASK_ASSIGNED,
            payload={"task_id": task.id, "user_id": assignee.id, "code": task.code, "title": task.title},
            dedupe_key=f"{KIND_TASK_ASSIGNED}:{task.id}:{assignee.id}:recurrence", now=now,
        )
        return task

    async def _fresh_actor(self, session: AsyncSession, actor: User) -> User:
        fresh = await users_repo.get_by_id(session, actor.id)
        if fresh is None or not fresh.can_use_bot:
            raise PermissionDenied("inactive")
        return fresh
