"""General (ad-hoc) tasks — handoff §4.3, §4.6, F3.

Every state change: permission check (re-read from DB) + one transaction with
the change, an ``AuditEvent`` and outbox rows; the Codecks sync hook runs after
commit.

Submission and review (IN_REVIEW, approval chains) arrive in M2.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from eventum_hq.core.db import Database
from eventum_hq.core.errors import InvalidTransition, NotFound, PermissionDenied, ValidationFailed
from eventum_hq.core.normalize import normalize_digits
from eventum_hq.core.timeutil import Clock, ensure_utc
from eventum_hq.integrations.sync import NoopSync, TaskSyncPort
from eventum_hq.models import (
    ApprovalChain,
    AuditEvent,
    Capability,
    Series,
    Task,
    TaskInput,
    TaskInputKind,
    TaskKind,
    TaskStatus,
    User,
)
from eventum_hq.repositories import audit as audit_repo
from eventum_hq.repositories import series as series_repo
from eventum_hq.repositories import tasks as tasks_repo
from eventum_hq.repositories import users as users_repo
from eventum_hq.services import audit
from eventum_hq.services.notifications import enqueue
from eventum_hq.services.permissions import (
    can_manage_task,
    can_view_task,
    has_capability,
    require_capability,
)
from eventum_hq.services.task_states import ensure_transition, is_open

ENTITY = "task"
TITLE_MAX = 200
DESCRIPTION_MAX = 3000
AT_RISK_WINDOW = timedelta(hours=24)

# Outbox kinds (rendered by bot/outbox.py)
KIND_TASK_ASSIGNED = "task.assigned"
KIND_TASK_UNASSIGNED = "task.unassigned"
KIND_TASK_DUE_CHANGED = "task.due_changed"
KIND_TASK_CANCELLED = "task.cancelled"

_CODE_RE = re.compile(r"^#?\s*[Tt]\s*-?\s*(\d{1,6})$")


def parse_task_code(text: str | None) -> str | None:
    """'T-0042', 't42', '#T0042', 'T-۴۲' → 'T-0042'. ``None`` if not a task code."""
    if not text:
        return None
    match = _CODE_RE.match(normalize_digits(text.strip()))
    return f"T-{int(match.group(1)):04d}" if match else None


class DeadlineState(StrEnum):
    NONE = "NONE"  # no deadline, already submitted, or closed
    OK = "OK"
    AT_RISK = "AT_RISK"  # due within 24h and not submitted yet
    OVERDUE = "OVERDUE"  # past due and not submitted yet


def deadline_state(task: Task, now: datetime) -> DeadlineState:
    """Lateness is judged on the first submission only (§4.7): review queue time never counts."""
    if task.due_at is None or not is_open(task.status) or task.first_submitted_at is not None:
        return DeadlineState.NONE
    if task.due_at < now:
        return DeadlineState.OVERDUE
    if task.due_at < now + AT_RISK_WINDOW:
        return DeadlineState.AT_RISK
    return DeadlineState.OK


class TaskFilter(StrEnum):
    OPEN = "open"
    OVERDUE = "overdue"
    AT_RISK = "risk"
    BY_USER = "user"
    BY_SERIES = "series"


@dataclass(slots=True)
class NewTask:
    title: str
    assignee_id: int
    due_at: datetime
    description: str | None = None
    attachments: list[dict[str, Any]] = field(default_factory=list)
    series_id: int | None = None
    approval_chain: ApprovalChain = ApprovalChain.FINAL


@dataclass(frozen=True, slots=True)
class TaskRow:
    task: Task
    assignee: User


@dataclass(frozen=True, slots=True)
class TaskView:
    task: Task
    assignee: User
    creator: User
    series: Series | None
    brief: TaskInput | None
    last_event: AuditEvent | None
    last_actor: User | None
    can_start: bool
    can_manage: bool


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    event: AuditEvent
    actor: User | None


class TaskService:
    def __init__(self, db: Database, clock: Clock, sync: TaskSyncPort | None = None) -> None:
        self._db = db
        self._clock = clock
        self._sync = sync or NoopSync()

    # ---- lookups for pickers ------------------------------------------------

    async def assignable_users(self) -> list[User]:
        async with self._db.read() as session:
            return list(await users_repo.list_active(session))

    async def active_series(self) -> list[Series]:
        async with self._db.read() as session:
            return list(await series_repo.list_active(session))

    # ---- create -----------------------------------------------------------

    async def create_generic(self, actor: User, data: NewTask) -> Task:
        now = self._clock.now()
        title = (data.title or "").strip()
        description = (data.description or "").strip() or None
        if not title:
            raise ValidationFailed("title_empty")
        if len(title) > TITLE_MAX:
            raise ValidationFailed("title_too_long")
        if description is not None and len(description) > DESCRIPTION_MAX:
            raise ValidationFailed("description_too_long")
        due_at = ensure_utc(data.due_at)
        chain = ApprovalChain(data.approval_chain)

        async with self._db.transaction() as session:
            fresh = await self._fresh_actor(session, actor)
            require_capability(fresh, Capability.CREATE_TASK)
            assignee = await self._active_user(session, data.assignee_id)
            if data.series_id is not None:
                series = await series_repo.get(session, data.series_id)
                if series is None or not series.is_active:
                    raise ValidationFailed("series_invalid")

            task = Task(
                code=f"tmp-{uuid.uuid4().hex[:10]}",
                kind=TaskKind.GENERIC,
                title=title,
                description=description,
                series_id=data.series_id,
                assignee_id=assignee.id,
                created_by=fresh.id,
                status=TaskStatus.TODO,
                approval_chain=chain,
                due_at=due_at,
                revision_round=0,
            )
            session.add(task)
            await session.flush()
            task.code = f"T-{task.id:04d}"

            if data.attachments:
                session.add(
                    TaskInput(
                        task_id=task.id,
                        kind=TaskInputKind.BRIEF,
                        text=description,
                        attachments=list(data.attachments),
                        provided_by=fresh.id,
                        provided_at=now,
                    )
                )
            await audit.record(
                session,
                actor_id=fresh.id,
                action="task.created",
                entity_type=ENTITY,
                entity_id=task.id,
                at=now,
                data={
                    "code": task.code,
                    "title": title,
                    "assignee_id": assignee.id,
                    "due_at": due_at.isoformat(),
                    "series_id": data.series_id,
                    "approval_chain": str(chain),
                    "brief_files": len(data.attachments),
                },
            )
            await self._notify(session, assignee, fresh, KIND_TASK_ASSIGNED, task, now)

        await self._sync.on_task_created(task.id)
        return task

    # ---- read ---------------------------------------------------------------

    async def get_view(
        self, viewer: User, *, task_id: int | None = None, code: str | None = None
    ) -> TaskView:
        async with self._db.read() as session:
            fresh = await self._fresh_actor(session, viewer)
            task = await self._load(session, task_id=task_id, code=code)
            if not can_view_task(fresh, task):
                raise PermissionDenied("task.view")
            people = await users_repo.get_many(session, {task.assignee_id, task.created_by})
            series = await series_repo.get(session, task.series_id) if task.series_id else None
            brief = await tasks_repo.latest_input(session, task.id, TaskInputKind.BRIEF)
            last = await audit_repo.last_for_entity(session, entity_type=ENTITY, entity_id=task.id)
            last_actor = None
            if last is not None and last.actor_id is not None:
                last_actor = people.get(last.actor_id) or await users_repo.get_by_id(
                    session, last.actor_id
                )
            open_ = is_open(task.status)
            return TaskView(
                task=task,
                assignee=people[task.assignee_id],
                creator=people[task.created_by],
                series=series,
                brief=brief,
                last_event=last,
                last_actor=last_actor,
                can_start=task.assignee_id == fresh.id
                and task.status in (TaskStatus.TODO, TaskStatus.CHANGES_REQUESTED),
                can_manage=open_ and can_manage_task(fresh, task),
            )

    async def list_my(self, viewer: User) -> list[TaskRow]:
        async with self._db.read() as session:
            fresh = await self._fresh_actor(session, viewer)
            tasks = await tasks_repo.list_open(session, assignee_id=fresh.id)
            return [TaskRow(t, fresh) for t in tasks]

    async def list_all(
        self, viewer: User, task_filter: TaskFilter | str, arg: int | None = None
    ) -> list[TaskRow]:
        task_filter = TaskFilter(task_filter)
        now = self._clock.now()
        async with self._db.read() as session:
            fresh = await self._fresh_actor(session, viewer)
            require_capability(fresh, Capability.VIEW_ALL_TASKS)
            if task_filter == TaskFilter.OPEN:
                tasks = await tasks_repo.list_open(session)
            elif task_filter == TaskFilter.OVERDUE:
                tasks = await tasks_repo.list_open(session, not_submitted=True, due_before=now)
            elif task_filter == TaskFilter.AT_RISK:
                tasks = await tasks_repo.list_open(
                    session, not_submitted=True, due_from=now, due_before=now + AT_RISK_WINDOW
                )
            elif task_filter == TaskFilter.BY_USER:
                tasks = await tasks_repo.list_open(session, assignee_id=arg)
            else:
                tasks = await tasks_repo.list_open(session, series_id=arg)
            people = await users_repo.get_many(session, {t.assignee_id for t in tasks})
            return [TaskRow(t, people[t.assignee_id]) for t in tasks]

    async def history(self, viewer: User, task_id: int) -> tuple[Task, list[HistoryEntry]]:
        async with self._db.read() as session:
            fresh = await self._fresh_actor(session, viewer)
            task = await self._load(session, task_id=task_id)
            if not can_view_task(fresh, task):
                raise PermissionDenied("task.view")
            events = await audit_repo.list_for_entity(session, entity_type=ENTITY, entity_id=task.id)
            people = await users_repo.get_many(
                session, {e.actor_id for e in events if e.actor_id is not None}
            )
            return task, [
                HistoryEntry(e, people.get(e.actor_id) if e.actor_id else None) for e in events
            ]

    async def can_view_all(self, viewer: User) -> bool:
        return has_capability(viewer, Capability.VIEW_ALL_TASKS)

    # ---- state changes ------------------------------------------------------

    async def start(self, actor: User, task_id: int) -> Task:
        now = self._clock.now()
        async with self._db.transaction() as session:
            fresh = await self._fresh_actor(session, actor)
            task = await self._load(session, task_id=task_id)
            if task.assignee_id != fresh.id:
                raise PermissionDenied("task.start")
            old = task.status
            ensure_transition(old, TaskStatus.IN_PROGRESS)
            task.status = TaskStatus.IN_PROGRESS
            await audit.record(
                session,
                actor_id=fresh.id,
                action="task.started",
                entity_type=ENTITY,
                entity_id=task.id,
                at=now,
                data={"from": str(old), "to": str(task.status)},
            )
        await self._sync.on_task_status_changed(task.id, str(old), str(task.status))
        return task

    async def cancel(self, actor: User, task_id: int) -> Task:
        now = self._clock.now()
        async with self._db.transaction() as session:
            fresh = await self._fresh_actor(session, actor)
            task = await self._load(session, task_id=task_id)
            if not can_manage_task(fresh, task):
                raise PermissionDenied("task.cancel")
            old = task.status
            ensure_transition(old, TaskStatus.CANCELLED)
            task.status = TaskStatus.CANCELLED
            task.review_stage = None
            await audit.record(
                session,
                actor_id=fresh.id,
                action="task.cancelled",
                entity_type=ENTITY,
                entity_id=task.id,
                at=now,
                data={"from": str(old), "to": str(task.status)},
            )
            assignee = await self._user(session, task.assignee_id)
            await self._notify(session, assignee, fresh, KIND_TASK_CANCELLED, task, now)
        await self._sync.on_task_status_changed(task.id, str(old), str(task.status))
        return task

    async def change_due(self, actor: User, task_id: int, due_at: datetime) -> Task:
        now = self._clock.now()
        due_at = ensure_utc(due_at)
        async with self._db.transaction() as session:
            fresh = await self._fresh_actor(session, actor)
            task = await self._load(session, task_id=task_id)
            if not can_manage_task(fresh, task):
                raise PermissionDenied("task.edit")
            if not is_open(task.status):
                raise InvalidTransition(str(task.status), "EDIT")
            if task.due_at == due_at:
                raise ValidationFailed("same_due")
            before = task.due_at
            task.due_at = due_at
            await audit.record(
                session,
                actor_id=fresh.id,
                action="task.due_changed",
                entity_type=ENTITY,
                entity_id=task.id,
                at=now,
                data={
                    "before": before.isoformat() if before else None,
                    "after": due_at.isoformat(),
                },
            )
            assignee = await self._user(session, task.assignee_id)
            await self._notify(session, assignee, fresh, KIND_TASK_DUE_CHANGED, task, now)
        await self._sync.on_task_updated(task.id)
        return task

    async def reassign(self, actor: User, task_id: int, new_assignee_id: int) -> Task:
        now = self._clock.now()
        async with self._db.transaction() as session:
            fresh = await self._fresh_actor(session, actor)
            task = await self._load(session, task_id=task_id)
            if not can_manage_task(fresh, task):
                raise PermissionDenied("task.reassign")
            if not is_open(task.status):
                raise InvalidTransition(str(task.status), "REASSIGN")
            if task.assignee_id == new_assignee_id:
                raise ValidationFailed("same_assignee")
            new_assignee = await self._active_user(session, new_assignee_id)
            old_assignee = await self._user(session, task.assignee_id)
            task.assignee_id = new_assignee.id
            await audit.record(
                session,
                actor_id=fresh.id,
                action="task.reassigned",
                entity_type=ENTITY,
                entity_id=task.id,
                at=now,
                data={"before": old_assignee.id, "after": new_assignee.id},
            )
            await self._notify(session, new_assignee, fresh, KIND_TASK_ASSIGNED, task, now)
            await self._notify(session, old_assignee, fresh, KIND_TASK_UNASSIGNED, task, now)
        await self._sync.on_task_updated(task.id)
        return task

    # ---- helpers -----------------------------------------------------------

    async def _fresh_actor(self, session: AsyncSession, actor: User) -> User:
        fresh = await users_repo.get_by_id(session, actor.id)
        if fresh is None or not fresh.can_use_bot:
            raise PermissionDenied("inactive")
        return fresh

    async def _load(
        self, session: AsyncSession, *, task_id: int | None = None, code: str | None = None
    ) -> Task:
        task = None
        if task_id is not None:
            task = await tasks_repo.get(session, task_id)
        elif code is not None:
            normalized = parse_task_code(code)
            task = await tasks_repo.get_by_code(session, normalized) if normalized else None
        if task is None:
            raise NotFound(f"task {task_id or code}")
        return task

    async def _user(self, session: AsyncSession, user_id: int) -> User:
        user = await users_repo.get_by_id(session, user_id)
        if user is None:
            raise NotFound(f"user {user_id}")
        return user

    async def _active_user(self, session: AsyncSession, user_id: int) -> User:
        user = await users_repo.get_by_id(session, user_id)
        if user is None or not user.can_use_bot:
            raise ValidationFailed("assignee_inactive")
        return user

    async def _notify(
        self,
        session: AsyncSession,
        recipient: User,
        actor: User,
        kind: str,
        task: Task,
        now: datetime,
    ) -> None:
        """Queue an urgent notification, except to the person who did the action."""
        if recipient.id == actor.id or not recipient.can_use_bot:
            return
        await enqueue(
            session,
            chat_id=recipient.telegram_id,
            kind=kind,
            payload={
                "task_id": task.id,
                "user_id": recipient.id,
                "code": task.code,
                "title": task.title,
            },
            dedupe_key=f"{kind}:{task.id}:{recipient.id}:{now.isoformat()}",
            now=now,
            urgent=True,
        )
