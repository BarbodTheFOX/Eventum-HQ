"""Reel flow (handoff §4.5, F4, F8) — kept isolated here so a V1 stage-template
engine can replace it later without touching the rest.

1. A CREATE_REEL user (Amin) creates a reel → ContentItem R-xxxx IN_PRODUCTION,
   an EDIT task (TODO, with TIMECODES) and a COVER task (BLOCKED until cover
   photos arrive, with COVER_TEXT). Deadlines are relative to the planned
   publish time (setting ``reel_offsets``); estimates come from ``reel_estimates``.
2. The edit assignee (Sina) delivers cover photos → copied to the archive,
   COVER_PHOTOS input on the cover task, cover task BLOCKED → TODO, cover
   assignee notified. Late photos are recorded on the reel (``photos_late``),
   i.e. on Sina, not on the cover designer.
3. Each task goes through delivery and L1 → FINAL review independently. Final
   approval of a reel task makes it DONE (v1.2) and calls :func:`on_task_finalized`.
4. When every task is DONE → READY_TO_PUBLISH and PUBLISH users get the card.
5. A PUBLISH user registers the publish links → PUBLISHED.
6. The creator (or a final approver) can cancel the reel → all open tasks CANCELLED.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from eventum_hq.core.db import Database
from eventum_hq.core.errors import InvalidTransition, NotFound, PermissionDenied, ValidationFailed
from eventum_hq.core.jalali import ESTIMATE_MAX_MINUTES
from eventum_hq.core.timeutil import Clock, ensure_utc
from eventum_hq.models import (
    ApprovalChain,
    Capability,
    ContentItem,
    ContentStatus,
    ContentSubtype,
    ContentType,
    Role,
    Series,
    Task,
    TaskInput,
    TaskInputKind,
    TaskKind,
    TaskStatus,
    User,
)
from eventum_hq.repositories import content as content_repo
from eventum_hq.repositories import reviews as reviews_repo
from eventum_hq.repositories import users as users_repo
from eventum_hq.services import audit
from eventum_hq.services.notifications import enqueue
from eventum_hq.services.permissions import has_capability, is_owner, stored_capabilities
from eventum_hq.services.task_states import ensure_transition, is_open

ENTITY = "content_item"
TITLE_MAX = 200
TEXT_MAX = 3000
MAX_LINKS = 10
DEFAULT_SERIES = "ریل روزانه"
DEFAULT_TRIAL_SERIES = "Trial Reels"
BLOCKED_WAITING_PHOTOS = "waiting_cover_photos"  # Task.blocked_reason code (text lives in bot/texts.py)

DEFAULT_OFFSETS = {"photos_after_create_h": 4, "edit_before_publish_h": 6, "cover_before_publish_h": 6}
DEFAULT_ESTIMATES = {"edit_normal_min": 45, "edit_motion_min": 100, "edit_trial_min": 30, "cover_min": 45}

KIND_REEL_PHOTOS_READY = "reel.photos_ready"
KIND_REEL_TASK_APPROVED = "reel.task_approved"
KIND_REEL_READY = "reel.ready"
KIND_REEL_PUBLISHED = "reel.published"
KIND_REEL_CANCELLED = "reel.cancelled"
KIND_TASK_ASSIGNED = "task.assigned"  # same card notification as general tasks

_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)
_CODE_RE = re.compile(r"^#?\s*[Rr]\s*-?\s*(\d{1,6})$")


def parse_reel_code(text: str | None) -> str | None:
    from eventum_hq.core.normalize import normalize_digits

    if not text:
        return None
    match = _CODE_RE.match(normalize_digits(text.strip()))
    return f"R-{int(match.group(1)):04d}" if match else None


# ---- plan (deadlines and estimates) ------------------------------------------------


@dataclass(frozen=True, slots=True)
class ReelPlan:
    photos_due_at: datetime
    edit_due_at: datetime
    cover_due_at: datetime
    edit_estimate: int
    cover_estimate: int


def compute_plan(
    *,
    now: datetime,
    publish_at: datetime,
    subtype: ContentSubtype,
    motion: bool,
    offsets: dict[str, Any],
    estimates: dict[str, Any],
) -> ReelPlan:
    """Default deadlines and estimates (handoff §4.5 step 3, F17)."""
    o = {**DEFAULT_OFFSETS, **(offsets or {})}
    e = {**DEFAULT_ESTIMATES, **(estimates or {})}
    edit_due = publish_at - timedelta(hours=o["edit_before_publish_h"])
    cover_due = publish_at - timedelta(hours=o["cover_before_publish_h"])
    photos_due = min(now + timedelta(hours=o["photos_after_create_h"]), edit_due)
    if subtype == ContentSubtype.TRIAL:
        edit_estimate = e["edit_trial_min"]
    else:
        edit_estimate = e["edit_motion_min"] if motion else e["edit_normal_min"]
    return ReelPlan(photos_due, edit_due, cover_due, int(edit_estimate), int(e["cover_min"]))


@dataclass(slots=True)
class NewReel:
    title: str
    subtype: ContentSubtype
    planned_publish_at: datetime
    timecodes: str
    cover_text: str
    edit_assignee_id: int
    cover_assignee_id: int
    series_id: int | None = None
    motion: bool = False
    # optional overrides chosen by the creator (None = default from the plan)
    photos_due_at: datetime | None = None
    edit_due_at: datetime | None = None
    cover_due_at: datetime | None = None
    edit_estimate: int | None = None
    cover_estimate: int | None = None


@dataclass(frozen=True, slots=True)
class ReelDefaults:
    edit_assignee: User | None
    cover_assignee: User | None
    series: Series | None
    trial_series: Series | None


@dataclass(frozen=True, slots=True)
class ReelView:
    item: ContentItem
    edit_task: Task | None
    cover_task: Task | None
    creator: User
    series: Series | None
    people: dict[int, User]
    can_cancel: bool
    can_publish: bool


def can_view_reel(user: User, item: ContentItem, tasks: list[Task]) -> bool:
    if not user.can_use_bot:
        return False
    return (
        item.created_by == user.id
        or any(t.assignee_id == user.id for t in tasks)
        or has_capability(user, Capability.VIEW_ALL_TASKS)
        or has_capability(user, Capability.PUBLISH)
        or has_capability(user, Capability.CREATE_REEL)
    )


def can_cancel_reel(user: User, item: ContentItem) -> bool:
    """Creator (Amin) or a final approver (Farid; the OWNER implicitly)."""
    return user.can_use_bot and (
        item.created_by == user.id or has_capability(user, Capability.APPROVE_FINAL)
    )


class ReelService:
    def __init__(self, db: Database, clock: Clock) -> None:
        self._db = db
        self._clock = clock

    # ---- defaults / plan ------------------------------------------------------

    async def defaults(self) -> ReelDefaults:
        async with self._db.read() as session:
            active = list(await users_repo.list_active(session))
            editor = next((u for u in active if u.role == Role.EDITOR), None)
            designer = next((u for u in active if u.role == Role.DESIGNER), None)
            series = await content_repo.series_by_name(session, DEFAULT_SERIES)
            trial = await content_repo.series_by_name(session, DEFAULT_TRIAL_SERIES)
            return ReelDefaults(editor, designer, series, trial)

    async def plan(self, publish_at: datetime, subtype: ContentSubtype, motion: bool) -> ReelPlan:
        async with self._db.read() as session:
            offsets = await content_repo.setting(session, "reel_offsets", DEFAULT_OFFSETS)
            estimates = await content_repo.setting(session, "reel_estimates", DEFAULT_ESTIMATES)
        return compute_plan(now=self._clock.now(), publish_at=ensure_utc(publish_at), subtype=subtype,
                            motion=motion, offsets=offsets, estimates=estimates)

    # ---- create ---------------------------------------------------------------

    async def create(self, actor: User, data: NewReel) -> ContentItem:
        now = self._clock.now()
        title = (data.title or "").strip()
        timecodes = (data.timecodes or "").strip()
        cover_text = (data.cover_text or "").strip()
        if not title:
            raise ValidationFailed("title_empty")
        if len(title) > TITLE_MAX:
            raise ValidationFailed("title_too_long")
        if not timecodes or not cover_text:
            raise ValidationFailed("reel_inputs_missing")
        if len(timecodes) > TEXT_MAX or len(cover_text) > TEXT_MAX:
            raise ValidationFailed("description_too_long")
        publish_at = ensure_utc(data.planned_publish_at)
        subtype = ContentSubtype(data.subtype)
        plan = await self.plan(publish_at, subtype, data.motion)
        photos_due = ensure_utc(data.photos_due_at) if data.photos_due_at else plan.photos_due_at
        edit_due = ensure_utc(data.edit_due_at) if data.edit_due_at else plan.edit_due_at
        cover_due = ensure_utc(data.cover_due_at) if data.cover_due_at else plan.cover_due_at
        if photos_due > edit_due:
            raise ValidationFailed("photos_after_edit")
        edit_estimate = data.edit_estimate if data.edit_estimate is not None else plan.edit_estimate
        cover_estimate = data.cover_estimate if data.cover_estimate is not None else plan.cover_estimate
        for minutes in (edit_estimate, cover_estimate):
            if not (0 < minutes <= ESTIMATE_MAX_MINUTES):
                raise ValidationFailed("estimate_invalid")

        async with self._db.transaction() as session:
            fresh = await _fresh(session, actor)
            if not has_capability(fresh, Capability.CREATE_REEL):
                raise PermissionDenied("reel.create")
            editor = await _active(session, data.edit_assignee_id)
            designer = await _active(session, data.cover_assignee_id)
            if data.series_id is not None:
                series = await session.get(Series, data.series_id)
                if series is None or not series.is_active:
                    raise ValidationFailed("series_invalid")

            item = ContentItem(
                code=f"tmp-{uuid.uuid4().hex[:10]}",
                type=ContentType.REEL,
                subtype=subtype,
                title=title,
                series_id=data.series_id,
                created_by=fresh.id,
                planned_publish_at=publish_at,
                status=ContentStatus.IN_PRODUCTION,
                photos_due_at=photos_due,
                photos_late=False,
                publish_links=[],
            )
            session.add(item)
            await session.flush()
            item.code = f"R-{item.id:04d}"

            edit = await self._new_task(session, item, TaskKind.EDIT, editor, fresh, edit_due, edit_estimate,
                                        TaskStatus.TODO, None)
            cover = await self._new_task(session, item, TaskKind.COVER, designer, fresh, cover_due,
                                         cover_estimate, TaskStatus.BLOCKED, BLOCKED_WAITING_PHOTOS)
            session.add_all([
                TaskInput(task_id=edit.id, content_item_id=item.id, kind=TaskInputKind.TIMECODES,
                          text=timecodes, attachments=[], provided_by=fresh.id, provided_at=now),
                TaskInput(task_id=cover.id, content_item_id=item.id, kind=TaskInputKind.COVER_TEXT,
                          text=cover_text, attachments=[], provided_by=fresh.id, provided_at=now),
            ])
            await audit.record(
                session, actor_id=fresh.id, action="reel.created", entity_type=ENTITY, entity_id=item.id,
                at=now,
                data={"code": item.code, "title": title, "subtype": str(subtype), "motion": data.motion,
                      "planned_publish_at": publish_at.isoformat(), "photos_due_at": photos_due.isoformat(),
                      "edit_task_id": edit.id, "cover_task_id": cover.id},
            )
            for task, person in ((edit, editor), (cover, designer)):
                await _notify(session, person, fresh, KIND_TASK_ASSIGNED, task, item, now)
            return item

    async def _new_task(
        self, session: AsyncSession, item: ContentItem, kind: TaskKind, assignee: User, creator: User,
        due: datetime, estimate: int, status: TaskStatus, blocked_reason: str | None,
    ) -> Task:
        now = self._clock.now()
        task = Task(
            code=f"tmp-{uuid.uuid4().hex[:10]}",
            content_item_id=item.id,
            kind=kind,
            title=item.title,
            series_id=item.series_id,
            assignee_id=assignee.id,
            created_by=creator.id,
            status=status,
            approval_chain=ApprovalChain.L1_FINAL,
            blocked_reason=blocked_reason,
            due_at=due,
            estimated_minutes=estimate,
            revision_round=0,
        )
        session.add(task)
        await session.flush()
        task.code = f"T-{task.id:04d}"
        await audit.record(
            session, actor_id=creator.id, action="task.created", entity_type="task", entity_id=task.id,
            at=now,
            data={"code": task.code, "reel": item.code, "kind": str(kind), "assignee_id": assignee.id,
                  "due_at": due.isoformat(), "estimated_minutes": estimate, "status": str(status)},
        )
        return task

    # ---- cover photos -------------------------------------------------------------

    async def deliver_cover_photos(self, actor: User, edit_task_id: int, attachments: list[dict[str, Any]]) -> ContentItem:
        now = self._clock.now()
        if not attachments:
            raise ValidationFailed("photos_empty")
        async with self._db.transaction() as session:
            fresh = await _fresh(session, actor)
            edit = await session.get(Task, edit_task_id)
            if edit is None or edit.kind != TaskKind.EDIT or edit.content_item_id is None:
                raise NotFound(f"edit task {edit_task_id}")
            if edit.assignee_id != fresh.id:
                raise PermissionDenied("reel.photos")
            item = await content_repo.get_item(session, edit.content_item_id)
            cover = await content_repo.task_of_kind(session, edit.content_item_id, TaskKind.COVER)
            if item is None or cover is None:
                raise NotFound(f"reel of task {edit_task_id}")
            if item.status != ContentStatus.IN_PRODUCTION or cover.status != TaskStatus.BLOCKED:
                raise InvalidTransition(str(cover.status), str(TaskStatus.TODO))

            session.add(TaskInput(task_id=cover.id, content_item_id=item.id, kind=TaskInputKind.COVER_PHOTOS,
                                  text=None, attachments=list(attachments), provided_by=fresh.id,
                                  provided_at=now))
            item.photos_delivered_at = now
            item.photos_late = item.photos_due_at is not None and now > item.photos_due_at
            ensure_transition(cover.status, TaskStatus.TODO)
            cover.status = TaskStatus.TODO
            cover.blocked_reason = None
            await audit.record(
                session, actor_id=fresh.id, action="reel.photos_delivered", entity_type=ENTITY,
                entity_id=item.id, at=now, data={"files": len(attachments), "late": item.photos_late},
            )
            await audit.record(
                session, actor_id=fresh.id, action="task.unblocked", entity_type="task", entity_id=cover.id,
                at=now, data={"from": "BLOCKED", "to": "TODO", "photos": len(attachments)},
            )
            designer = await users_repo.get_by_id(session, cover.assignee_id)
            if designer is not None:
                await _notify(session, designer, fresh, KIND_REEL_PHOTOS_READY, cover, item, now)
            return item

    # ---- views ------------------------------------------------------------------

    async def view(self, viewer: User, *, item_id: int | None = None, code: str | None = None) -> ReelView:
        async with self._db.read() as session:
            fresh = await _fresh(session, viewer)
            item = None
            if item_id is not None:
                item = await content_repo.get_item(session, item_id)
            elif code is not None:
                normalized = parse_reel_code(code)
                item = await content_repo.get_item_by_code(session, normalized) if normalized else None
            if item is None:
                raise NotFound(f"reel {item_id or code}")
            return await self._view(session, fresh, item)

    async def _view(self, session: AsyncSession, viewer: User, item: ContentItem) -> ReelView:
        tasks = list(await content_repo.tasks_of(session, item.id))
        if not can_view_reel(viewer, item, tasks):
            raise PermissionDenied("reel.view")
        people = await users_repo.get_many(session, {item.created_by, *(t.assignee_id for t in tasks)})
        series = await session.get(Series, item.series_id) if item.series_id else None
        edit = next((t for t in tasks if t.kind == TaskKind.EDIT), None)
        cover = next((t for t in tasks if t.kind == TaskKind.COVER), None)
        return ReelView(
            item=item, edit_task=edit, cover_task=cover, creator=people[item.created_by], series=series,
            people=people,
            can_cancel=item.status in (ContentStatus.IN_PRODUCTION, ContentStatus.READY_TO_PUBLISH)
            and can_cancel_reel(viewer, item),
            can_publish=item.status == ContentStatus.READY_TO_PUBLISH
            and has_capability(viewer, Capability.PUBLISH),
        )

    async def ready_list(self, viewer: User) -> list[ReelView]:
        async with self._db.read() as session:
            fresh = await _fresh(session, viewer)
            if not has_capability(fresh, Capability.PUBLISH):
                raise PermissionDenied("reel.publish")
            items = await content_repo.items_with_status(session, ContentStatus.READY_TO_PUBLISH)
            return [await self._view(session, fresh, item) for item in items]

    async def final_files(self, item_id: int) -> list[dict[str, Any]]:
        """Approved video and cover files (from their final submissions), for the ready card."""
        async with self._db.read() as session:
            files: list[dict[str, Any]] = []
            for output in await content_repo.outputs_of(session, item_id):
                submission = await reviews_repo.get_submission(session, output.submission_id)
                if submission is not None:
                    files.extend(submission.attachments)
            return files

    # ---- publish / cancel ----------------------------------------------------------

    async def publish(self, actor: User, item_id: int, links: list[str],
                      published_at: datetime | None = None) -> ContentItem:
        now = self._clock.now()
        links = [link.strip() for link in links if link and link.strip()]
        if not links or len(links) > MAX_LINKS or not all(_URL_RE.match(link) for link in links):
            raise ValidationFailed("links_invalid")
        when = ensure_utc(published_at) if published_at else now
        async with self._db.transaction() as session:
            fresh = await _fresh(session, actor)
            if not has_capability(fresh, Capability.PUBLISH):
                raise PermissionDenied("reel.publish")
            item = await content_repo.get_item(session, item_id)
            if item is None:
                raise NotFound(f"reel {item_id}")
            if item.status != ContentStatus.READY_TO_PUBLISH:
                raise InvalidTransition(str(item.status), str(ContentStatus.PUBLISHED))
            item.status = ContentStatus.PUBLISHED
            item.published_at = when
            item.published_by = fresh.id
            item.publish_links = links
            await audit.record(
                session, actor_id=fresh.id, action="reel.published", entity_type=ENTITY, entity_id=item.id,
                at=now, data={"links": links, "published_at": when.isoformat()},
            )
            creator = await users_repo.get_by_id(session, item.created_by)
            if creator is not None:
                await _notify(session, creator, fresh, KIND_REEL_PUBLISHED, None, item, now)
            return item

    async def cancel(self, actor: User, item_id: int) -> ContentItem:
        now = self._clock.now()
        async with self._db.transaction() as session:
            fresh = await _fresh(session, actor)
            item = await content_repo.get_item(session, item_id)
            if item is None:
                raise NotFound(f"reel {item_id}")
            if not can_cancel_reel(fresh, item):
                raise PermissionDenied("reel.cancel")
            if item.status not in (ContentStatus.IN_PRODUCTION, ContentStatus.READY_TO_PUBLISH):
                raise InvalidTransition(str(item.status), str(ContentStatus.CANCELLED))
            old = item.status
            item.status = ContentStatus.CANCELLED
            notified: set[int] = set()
            for task in await content_repo.tasks_of(session, item.id):
                if not is_open(task.status):
                    continue
                before = task.status
                task.status = TaskStatus.CANCELLED
                task.review_stage = None
                await audit.record(
                    session, actor_id=fresh.id, action="task.cancelled", entity_type="task",
                    entity_id=task.id, at=now, data={"from": str(before), "to": "CANCELLED", "reel": item.code},
                )
                if task.assignee_id not in notified:
                    notified.add(task.assignee_id)
                    person = await users_repo.get_by_id(session, task.assignee_id)
                    if person is not None:
                        await _notify(session, person, fresh, KIND_REEL_CANCELLED, task, item, now)
            await audit.record(
                session, actor_id=fresh.id, action="reel.cancelled", entity_type=ENTITY, entity_id=item.id,
                at=now, data={"from": str(old)},
            )
            return item


# ---- hook called by ReviewService inside its transaction ------------------------------


async def on_task_finalized(session: AsyncSession, task: Task, actor: User, now: datetime) -> None:
    """A reel task got its final approval (now DONE). Tell the creator; maybe mark the reel ready."""
    if task.content_item_id is None:
        return
    item = await content_repo.get_item(session, task.content_item_id)
    if item is None:
        return
    creator = await users_repo.get_by_id(session, item.created_by)
    if creator is not None:
        await _notify(session, creator, actor, KIND_REEL_TASK_APPROVED, task, item, now)
    if item.status != ContentStatus.IN_PRODUCTION:
        return
    tasks = [t for t in await content_repo.tasks_of(session, item.id) if t.status != TaskStatus.CANCELLED]
    if not tasks or any(t.status != TaskStatus.DONE for t in tasks):
        return
    item.status = ContentStatus.READY_TO_PUBLISH
    await audit.record(session, actor_id=actor.id, action="reel.ready", entity_type=ENTITY,
                       entity_id=item.id, at=now, data={})
    active = list(await users_repo.list_active(session))
    publishers = [u for u in active if Capability.PUBLISH in stored_capabilities(u)]
    for person in publishers or [u for u in active if is_owner(u)]:
        await enqueue(
            session, chat_id=person.telegram_id, kind=KIND_REEL_READY,
            payload={"content_item_id": item.id, "user_id": person.id, "code": item.code, "title": item.title},
            dedupe_key=f"{KIND_REEL_READY}:{item.id}:{person.id}", now=now, urgent=True,
        )


# ---- helpers -----------------------------------------------------------------------


async def _fresh(session: AsyncSession, actor: User) -> User:
    fresh = await users_repo.get_by_id(session, actor.id)
    if fresh is None or not fresh.can_use_bot:
        raise PermissionDenied("inactive")
    return fresh


async def _active(session: AsyncSession, user_id: int) -> User:
    user = await users_repo.get_by_id(session, user_id)
    if user is None or not user.can_use_bot:
        raise ValidationFailed("assignee_inactive")
    return user


async def _notify(
    session: AsyncSession, recipient: User, actor: User, kind: str, task: Task | None, item: ContentItem,
    now: datetime,
) -> None:
    if recipient.id == actor.id or not recipient.can_use_bot:
        return
    payload: dict[str, Any] = {"user_id": recipient.id, "content_item_id": item.id, "reel_code": item.code,
                               "title": item.title}
    if task is not None:
        payload.update(task_id=task.id, code=task.code, task_kind=str(task.kind))
    await enqueue(
        session, chat_id=recipient.telegram_id, kind=kind, payload=payload,
        dedupe_key=f"{kind}:{item.id}:{task.id if task else 0}:{recipient.id}:{now.isoformat()}",
        now=now, urgent=True,
    )
