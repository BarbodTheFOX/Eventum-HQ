"""Offboarding (F15, handoff §4.11) and the member list of «👥 تیم».

Only holders of ``MANAGE_USERS`` (DIRECTOR, and the OWNER implicitly) may use it.

Deactivating a user:
* ``is_active = false`` + ``deactivated_at``; their name and history stay everywhere;
* an active delegation that involves them is revoked; their pending notifications
  are cancelled (they can no longer use the bot);
* their open tasks and active recurrences are listed for hand-over — all tasks
  to one person, or one by one; recurrences one by one (a recurrence whose
  assignee is inactive creates nothing until it is reassigned);
* their stored capabilities are reported, marking the ones nobody else active
  holds (e.g. REVIEW_L1, PUBLISH), and the OWNER(s) get the same warning.

Hand-over here only moves work *away from inactive users*; normal reassignment
of active people's tasks stays on the task card.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eventum_hq.core.db import Database
from eventum_hq.core.errors import InvalidTransition, NotFound, PermissionDenied, ValidationFailed
from eventum_hq.core.timeutil import Clock
from eventum_hq.integrations.sync import NoopSync, TaskSyncPort
from eventum_hq.models import AccessStatus, Capability, Recurrence, Role, Task, User
from eventum_hq.repositories import notifications as notifications_repo
from eventum_hq.repositories import reviews as reviews_repo
from eventum_hq.repositories import tasks as tasks_repo
from eventum_hq.repositories import users as users_repo
from eventum_hq.services import audit
from eventum_hq.services.notifications import enqueue
from eventum_hq.services.permissions import require_capability, stored_capabilities
from eventum_hq.services.task_states import is_open
from eventum_hq.services.tasks import KIND_TASK_ASSIGNED

ENTITY = "user"
KIND_USER_DEACTIVATED = "user.deactivated"


@dataclass(frozen=True, slots=True)
class CapabilityGap:
    capability: Capability
    covered: bool  # another active user still has it stored


@dataclass(frozen=True, slots=True)
class MemberRow:
    user: User
    open_tasks: int
    recurrences: int


@dataclass(frozen=True, slots=True)
class MemberView:
    user: User
    open_tasks: list[Task]
    recurrences: list[Recurrence]
    capabilities: list[CapabilityGap]
    can_deactivate: bool
    delegation_revoked: bool = False


async def _fresh_manager(session: AsyncSession, actor: User) -> User:
    fresh = await users_repo.get_by_id(session, actor.id)
    if fresh is None or not fresh.can_use_bot:
        raise PermissionDenied("inactive")
    require_capability(fresh, Capability.MANAGE_USERS)
    return fresh


async def _active_recurrences(session: AsyncSession, assignee_id: int | None = None) -> list[Recurrence]:
    query = select(Recurrence).where(Recurrence.is_active.is_(True))
    if assignee_id is not None:
        query = query.where(Recurrence.assignee_id == assignee_id)
    result = await session.execute(query.order_by(Recurrence.id))
    return list(result.scalars().all())


async def _capability_gaps(session: AsyncSession, user: User, stored: list[str]) -> list[CapabilityGap]:
    others = [u for u in await users_repo.list_active(session) if u.id != user.id]
    known = {c.value for c in Capability}
    gaps = []
    for value in stored:
        if value not in known:
            continue
        cap = Capability(value)
        gaps.append(CapabilityGap(cap, any(cap in stored_capabilities(o) for o in others)))
    return gaps


class OffboardingService:
    def __init__(self, db: Database, clock: Clock, sync: TaskSyncPort | None = None) -> None:
        self._db = db
        self._clock = clock
        self._sync = sync or NoopSync()

    # ---- reads ---------------------------------------------------------------------

    async def members(self, actor: User) -> list[MemberRow]:
        """Active team members with their open work (for the member list)."""
        async with self._db.read() as session:
            await _fresh_manager(session, actor)
            users = list(await users_repo.list_active(session))
            return [await self._row(session, u) for u in users]

    async def pending_handovers(self, actor: User) -> list[MemberRow]:
        """Deactivated people who still have open tasks or active recurrences."""
        async with self._db.read() as session:
            await _fresh_manager(session, actor)
            result = await session.execute(
                select(User).where(User.is_active.is_(False), User.deactivated_at.is_not(None))
                .order_by(User.deactivated_at, User.id)
            )
            rows = [await self._row(session, u) for u in result.scalars().all()]
            return [r for r in rows if r.open_tasks or r.recurrences]

    async def orphan_recurrences(self, actor: User) -> int:
        """Active recurrences whose assignee can no longer use the bot (they create nothing)."""
        async with self._db.read() as session:
            await _fresh_manager(session, actor)
            recurrences = await _active_recurrences(session)
            people = await users_repo.get_many(session, {r.assignee_id for r in recurrences})
            return sum(1 for r in recurrences if r.assignee_id not in people
                       or not people[r.assignee_id].can_use_bot)

    async def member(self, actor: User, user_id: int) -> MemberView:
        async with self._db.read() as session:
            fresh = await _fresh_manager(session, actor)
            user = await users_repo.get_by_id(session, user_id)
            if user is None or user.access_status != AccessStatus.APPROVED:
                raise NotFound(f"user {user_id}")
            return await self._view(session, fresh, user)

    async def assignable(self, actor: User, exclude_user_id: int) -> list[User]:
        """Active people work can be handed to."""
        async with self._db.read() as session:
            await _fresh_manager(session, actor)
            return [u for u in await users_repo.list_active(session) if u.id != exclude_user_id]

    # ---- deactivate ------------------------------------------------------------------

    async def deactivate(self, actor: User, user_id: int) -> MemberView:
        now = self._clock.now()
        async with self._db.transaction() as session:
            fresh = await _fresh_manager(session, actor)
            user = await users_repo.get_by_id(session, user_id)
            if user is None or user.access_status != AccessStatus.APPROVED:
                raise NotFound(f"user {user_id}")
            if user.id == fresh.id:
                raise ValidationFailed("deactivate_self")
            if user.role == Role.OWNER:
                raise ValidationFailed("deactivate_owner")
            if not user.is_active:
                raise InvalidTransition("INACTIVE", "DEACTIVATE")

            stored = list(user.capabilities or [])
            user.is_active = False
            user.deactivated_at = now
            gaps = await _capability_gaps(session, user, stored)

            revoked = None
            delegation = await reviews_repo.active_delegation(session, now)
            if delegation is not None and user.id in (delegation.from_user_id, delegation.to_user_id):
                delegation.revoked_at = now
                revoked = delegation.id
                await audit.record(session, actor_id=fresh.id, action="delegation.revoked",
                                   entity_type="delegation", entity_id=delegation.id, at=now,
                                   data={"reason": "offboarding", "user_id": user.id})
            cancelled = await notifications_repo.cancel_pending_for_chat(session, user.telegram_id)

            open_tasks = list(await tasks_repo.list_open(session, assignee_id=user.id))
            recurrences = await _active_recurrences(session, user.id)
            await audit.record(
                session, actor_id=fresh.id, action="user.deactivated", entity_type=ENTITY, entity_id=user.id,
                at=now,
                data={"role": str(user.role), "capabilities": stored,
                      "open_tasks": [t.id for t in open_tasks], "recurrences": [r.id for r in recurrences],
                      "delegation_revoked": revoked, "notifications_cancelled": cancelled},
            )
            payload = {
                "name": user.full_name, "role": str(user.role),
                "missing": [g.capability.value for g in gaps if not g.covered],
                "open_tasks": len(open_tasks), "recurrences": len(recurrences),
                "actor_name": fresh.full_name,
            }
            for owner in await users_repo.list_active_owners(session):
                if owner.id == fresh.id:
                    continue  # they see the same summary on screen
                await enqueue(session, chat_id=owner.telegram_id, kind=KIND_USER_DEACTIVATED,
                              payload={**payload, "user_id": owner.id},
                              dedupe_key=f"{KIND_USER_DEACTIVATED}:{user.id}:{owner.id}:{now.isoformat()}",
                              now=now, urgent=True)
            return MemberView(user=user, open_tasks=open_tasks, recurrences=recurrences, capabilities=gaps,
                              can_deactivate=False, delegation_revoked=revoked is not None)

    # ---- hand-over ---------------------------------------------------------------------

    async def transfer_task(self, actor: User, task_id: int, to_user_id: int) -> Task:
        now = self._clock.now()
        async with self._db.transaction() as session:
            fresh = await _fresh_manager(session, actor)
            task = await tasks_repo.get(session, task_id)
            if task is None:
                raise NotFound(f"task {task_id}")
            target = await self._target(session, to_user_id)
            await self._move_task(session, fresh, task, target, now)
        await self._sync.on_task_updated(task.id)
        return task

    async def transfer_all(self, actor: User, from_user_id: int, to_user_id: int) -> list[Task]:
        """Every open task of an inactive user to one person (recurrences stay one by one)."""
        now = self._clock.now()
        async with self._db.transaction() as session:
            fresh = await _fresh_manager(session, actor)
            source = await users_repo.get_by_id(session, from_user_id)
            if source is None:
                raise NotFound(f"user {from_user_id}")
            if source.can_use_bot:
                raise ValidationFailed("handover_active_user")
            target = await self._target(session, to_user_id)
            tasks = list(await tasks_repo.list_open(session, assignee_id=source.id))
            for task in tasks:
                await self._move_task(session, fresh, task, target, now)
        for task in tasks:
            await self._sync.on_task_updated(task.id)
        return tasks

    async def reassign_recurrence(self, actor: User, recurrence_id: int, to_user_id: int) -> Recurrence:
        now = self._clock.now()
        async with self._db.transaction() as session:
            fresh = await _fresh_manager(session, actor)
            recurrence = await session.get(Recurrence, recurrence_id)
            if recurrence is None or not recurrence.is_active:
                raise NotFound(f"recurrence {recurrence_id}")
            current = await users_repo.get_by_id(session, recurrence.assignee_id)
            if current is not None and current.can_use_bot:
                raise ValidationFailed("handover_active_user")
            target = await self._target(session, to_user_id)
            before = recurrence.assignee_id
            recurrence.assignee_id = target.id
            await audit.record(session, actor_id=fresh.id, action="recurrence.reassigned",
                               entity_type="recurrence", entity_id=recurrence.id, at=now,
                               data={"before": before, "after": target.id, "reason": "offboarding"})
            return recurrence

    # ---- helpers -------------------------------------------------------------------------

    async def _row(self, session: AsyncSession, user: User) -> MemberRow:
        open_tasks = await tasks_repo.list_open(session, assignee_id=user.id)
        recurrences = await _active_recurrences(session, user.id)
        return MemberRow(user, len(open_tasks), len(recurrences))

    async def _view(self, session: AsyncSession, actor: User, user: User) -> MemberView:
        open_tasks = list(await tasks_repo.list_open(session, assignee_id=user.id))
        recurrences = await _active_recurrences(session, user.id)
        gaps = await _capability_gaps(session, user, list(user.capabilities or []))
        can_deactivate = user.is_active and user.id != actor.id and user.role != Role.OWNER
        return MemberView(user, open_tasks, recurrences, gaps, can_deactivate)

    async def _target(self, session: AsyncSession, user_id: int) -> User:
        target = await users_repo.get_by_id(session, user_id)
        if target is None or not target.can_use_bot:
            raise ValidationFailed("assignee_inactive")
        return target

    async def _move_task(self, session: AsyncSession, actor: User, task: Task, target: User,
                         now: datetime) -> None:
        if not is_open(task.status):
            raise InvalidTransition(str(task.status), "REASSIGN")
        current = await users_repo.get_by_id(session, task.assignee_id)
        if current is not None and current.can_use_bot:
            raise ValidationFailed("handover_active_user")
        before = task.assignee_id
        task.assignee_id = target.id
        await audit.record(session, actor_id=actor.id, action="task.reassigned", entity_type="task",
                           entity_id=task.id, at=now,
                           data={"before": before, "after": target.id, "reason": "offboarding"})
        if target.id != actor.id:
            await enqueue(
                session, chat_id=target.telegram_id, kind=KIND_TASK_ASSIGNED,
                payload={"task_id": task.id, "user_id": target.id, "code": task.code, "title": task.title},
                dedupe_key=f"{KIND_TASK_ASSIGNED}:{task.id}:{target.id}:{now.isoformat()}", now=now,
                urgent=True,
            )
