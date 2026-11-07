"""Delivery, review, approval chains and the final "done" step (handoff §4.4, §4.7, §4.8, v1.2).

Chains:
* ``NONE``     — no review: the assignee's "✅ done" → DONE.
* ``FINAL``    — Farid (stored APPROVE_FINAL) approves; during a delegation, the delegate.
* ``L1_FINAL`` — Amin (REVIEW_L1), then Farid. During a delegation the delegate's
                 L1 approval is final.

After final approval a GENERIC task becomes APPROVED (waiting for the assignee's
"🏁 done" after upload); reel tasks (M3) go straight to DONE.

Concurrency lock: a decision names (submission_id, version, stage). If a newer
version arrived or someone else already decided, it is refused with AlreadyDecided.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from eventum_hq.core.db import Database
from eventum_hq.core.errors import (
    AlreadyDecided,
    InvalidTransition,
    NotFound,
    PermissionDenied,
    ValidationFailed,
)
from eventum_hq.core.normalize import normalize_text
from eventum_hq.core.timeutil import Clock
from eventum_hq.integrations.sync import NoopSync, TaskSyncPort
from eventum_hq.models import (
    ApprovalChain,
    Capability,
    Output,
    OutputType,
    Review,
    ReviewDecision,
    ReviewStage,
    Series,
    Submission,
    Task,
    TaskKind,
    TaskStatus,
    User,
)
from eventum_hq.repositories import reviews as reviews_repo
from eventum_hq.repositories import series as series_repo
from eventum_hq.repositories import tasks as tasks_repo
from eventum_hq.repositories import users as users_repo
from eventum_hq.services import audit
from eventum_hq.services.delegations import active_delegate_id
from eventum_hq.services.notifications import enqueue
from eventum_hq.services.permissions import (
    can_manage_task,
    has_capability,
    is_owner,
    stored_capabilities,
)
from eventum_hq.services.task_states import ensure_transition
from eventum_hq.services.tasks import TaskRow

ENTITY = "task"
NOTE_MAX = 3000
MAX_LINKS = 20
MAX_FILES = 30

KIND_REVIEW_REQUESTED = "review.requested"
KIND_REVIEW_L1_APPROVED = "review.l1_approved"
KIND_REVIEW_APPROVED = "review.approved"
KIND_REVIEW_CHANGES = "review.changes"
KIND_TASK_DONE = "task.done"

SUBMITTABLE = (TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.CHANGES_REQUESTED)


@dataclass(frozen=True, slots=True)
class ReviewView:
    task: Task
    submission: Submission
    assignee: User
    series: Series | None
    stage: ReviewStage
    can_decide: bool


class ReviewService:
    def __init__(self, db: Database, clock: Clock, sync: TaskSyncPort | None = None) -> None:
        self._db = db
        self._clock = clock
        self._sync = sync or NoopSync()

    # ---- delivery ------------------------------------------------------------

    async def next_version(self, task_id: int) -> int:
        async with self._db.read() as session:
            return await reviews_repo.max_version(session, task_id) + 1

    async def submit(
        self,
        actor: User,
        task_id: int,
        *,
        attachments: list[dict[str, Any]],
        links: list[str],
        note: str | None,
    ) -> Submission:
        now = self._clock.now()
        note = (note or "").strip() or None
        if not attachments and not links:
            raise ValidationFailed("submission_empty")
        if len(attachments) > MAX_FILES or len(links) > MAX_LINKS:
            raise ValidationFailed("submission_too_big")
        if note is not None and len(note) > NOTE_MAX:
            raise ValidationFailed("note_too_long")

        async with self._db.transaction() as session:
            fresh = await self._fresh(session, actor)
            task = await self._task(session, task_id)
            if task.assignee_id != fresh.id:
                raise PermissionDenied("task.submit")
            if task.approval_chain == ApprovalChain.NONE:
                raise InvalidTransition(str(task.status), "SUBMIT_NONE_CHAIN")
            if task.status not in SUBMITTABLE:
                raise InvalidTransition(str(task.status), str(TaskStatus.IN_REVIEW))
            old_status = task.status
            ensure_transition(old_status, TaskStatus.IN_REVIEW)

            stage = await self._stage_after_submit(session, task, old_status)
            version = await reviews_repo.max_version(session, task.id) + 1
            submission = Submission(
                task_id=task.id,
                version=version,
                submitted_by=fresh.id,
                note=note,
                attachments=list(attachments),
                links=list(links),
                submitted_at=now,
            )
            session.add(submission)
            if task.first_submitted_at is None:
                task.first_submitted_at = now
            task.status = TaskStatus.IN_REVIEW
            task.review_stage = stage
            await session.flush()
            await audit.record(
                session, actor_id=fresh.id, action="task.submitted", entity_type=ENTITY,
                entity_id=task.id, at=now,
                data={"version": version, "stage": str(stage), "files": len(attachments),
                      "links": len(links), "from": str(old_status)},
            )
            await self._notify_reviewers(session, task, submission, stage, now)
        await self._sync.on_task_status_changed(task.id, str(old_status), str(TaskStatus.IN_REVIEW))
        return submission

    async def _stage_after_submit(
        self, session: AsyncSession, task: Task, old_status: TaskStatus
    ) -> ReviewStage:
        first_stage = ReviewStage.L1 if task.approval_chain == ApprovalChain.L1_FINAL else ReviewStage.FINAL
        if old_status != TaskStatus.CHANGES_REQUESTED or task.review_stage is None:
            return first_stage
        returns = await reviews_repo.setting(session, "revision_returns_to_requesting_stage", True)
        # §4.4: the new version goes straight back to the stage that asked for changes
        return task.review_stage if returns else first_stage

    # ---- queues and cards ------------------------------------------------------

    async def queue(self, viewer: User, stage: ReviewStage | str) -> list[TaskRow]:
        stage = ReviewStage(stage)
        now = self._clock.now()
        async with self._db.read() as session:
            fresh = await self._fresh(session, viewer)
            if not await self._may_review(session, fresh, stage, now):
                raise PermissionDenied(f"review.{stage}")
            tasks = await reviews_repo.tasks_in_review(session, stage)
            people = await users_repo.get_many(session, {t.assignee_id for t in tasks})
            return [TaskRow(t, people[t.assignee_id]) for t in tasks]

    async def review_view(self, viewer: User, task_id: int) -> ReviewView:
        now = self._clock.now()
        async with self._db.read() as session:
            fresh = await self._fresh(session, viewer)
            task = await self._task(session, task_id)
            if task.status != TaskStatus.IN_REVIEW or task.review_stage is None:
                raise AlreadyDecided(str(task.status))
            stage = task.review_stage
            if not await self._may_review(session, fresh, stage, now):
                raise PermissionDenied(f"review.{stage}")
            submission = await reviews_repo.latest_submission(session, task.id)
            if submission is None:
                raise NotFound(f"submission for task {task.id}")
            assignee = await users_repo.get_by_id(session, task.assignee_id)
            series = await series_repo.get(session, task.series_id) if task.series_id else None
            assert assignee is not None
            return ReviewView(task, submission, assignee, series, stage, True)

    async def review_detail(self, viewer: User, review_id: int) -> tuple[Review, Task]:
        """For the assignee's 'changes requested' card (notes)."""
        async with self._db.read() as session:
            fresh = await self._fresh(session, viewer)
            review = await reviews_repo.get_review(session, review_id)
            if review is None:
                raise NotFound(f"review {review_id}")
            submission = await reviews_repo.get_submission(session, review.submission_id)
            assert submission is not None
            task = await self._task(session, submission.task_id)
            if task.assignee_id != fresh.id and not has_capability(fresh, Capability.VIEW_ALL_TASKS):
                raise PermissionDenied("review.view")
            return review, task

    async def task_for_submission(self, submission_id: int) -> Task:
        async with self._db.read() as session:
            submission = await reviews_repo.get_submission(session, submission_id)
            if submission is None:
                raise NotFound(f"submission {submission_id}")
            return await self._task(session, submission.task_id)

    async def latest_submission(self, task_id: int) -> Submission | None:
        async with self._db.read() as session:
            return await reviews_repo.latest_submission(session, task_id)

    # ---- decisions -------------------------------------------------------------

    async def approve(self, actor: User, submission_id: int, version: int, stage: ReviewStage | str) -> Task:
        return await self._decide(actor, submission_id, version, ReviewStage(stage), approve=True,
                                  note_text=None, note_attachments=[])

    async def request_changes(
        self, actor: User, submission_id: int, version: int, stage: ReviewStage | str, *,
        note_text: str | None, note_attachments: list[dict[str, Any]],
    ) -> Task:
        note_text = (note_text or "").strip() or None
        if note_text is None and not note_attachments:
            raise ValidationFailed("notes_empty")
        if note_text is not None and len(note_text) > NOTE_MAX:
            raise ValidationFailed("note_too_long")
        return await self._decide(actor, submission_id, version, ReviewStage(stage), approve=False,
                                  note_text=note_text, note_attachments=note_attachments)

    async def _decide(
        self, actor: User, submission_id: int, version: int, stage: ReviewStage, *, approve: bool,
        note_text: str | None, note_attachments: list[dict[str, Any]],
    ) -> Task:
        now = self._clock.now()
        async with self._db.transaction() as session:
            fresh = await self._fresh(session, actor)
            submission = await reviews_repo.get_submission(session, submission_id)
            if submission is None or submission.version != version:
                raise AlreadyDecided("STALE")
            task = await self._task(session, submission.task_id)
            latest = await reviews_repo.latest_submission(session, task.id)
            # concurrency lock (§4.8): newer version, other decision, or stage moved on
            if (
                task.status != TaskStatus.IN_REVIEW
                or latest is None
                or latest.id != submission.id
                or task.review_stage != stage
            ):
                raise AlreadyDecided(str(task.status))

            delegate_id = await active_delegate_id(session, now)
            is_delegate = delegate_id == fresh.id
            if not await self._may_review(session, fresh, stage, now):
                raise PermissionDenied(f"review.{stage}")

            old_status = task.status
            final = False
            delegated = False
            if approve:
                if stage == ReviewStage.L1:
                    final = is_delegate  # delegation: L1 approval is the final approval
                    delegated = is_delegate
                else:
                    final = True
                    delegated = is_delegate and not has_capability(fresh, Capability.APPROVE_FINAL)
            elif stage == ReviewStage.FINAL:
                delegated = is_delegate and not has_capability(fresh, Capability.APPROVE_FINAL)

            review = Review(
                submission_id=submission.id,
                stage=stage,
                reviewer_id=fresh.id,
                decision=ReviewDecision.APPROVED if approve else ReviewDecision.CHANGES_REQUESTED,
                note_text=note_text,
                note_attachments=list(note_attachments),
                delegated=delegated,
                decided_at=now,
            )
            session.add(review)
            await session.flush()
            assignee = await users_repo.get_by_id(session, task.assignee_id)
            assert assignee is not None

            if not approve:
                ensure_transition(old_status, TaskStatus.CHANGES_REQUESTED)
                task.status = TaskStatus.CHANGES_REQUESTED
                task.revision_round += 1
                # keep review_stage: the resubmission returns to this stage (§4.4)
                action = "review.changes_requested"
                await self._notify(session, assignee, fresh, KIND_REVIEW_CHANGES, task, now,
                                   extra={"review_id": review.id})
            elif not final:
                task.review_stage = ReviewStage.FINAL
                action = "review.approved"
                await self._notify(session, assignee, fresh, KIND_REVIEW_L1_APPROVED, task, now)
                await self._notify_reviewers(session, task, submission, ReviewStage.FINAL, now)
            else:
                target = TaskStatus.APPROVED if task.kind == TaskKind.GENERIC else TaskStatus.DONE
                ensure_transition(old_status, target)
                task.status = target
                task.review_stage = None
                if target == TaskStatus.DONE:
                    task.completed_at = now
                await self._create_output(session, task, submission, assignee, now)
                action = "review.approved"
                await self._notify(session, assignee, fresh, KIND_REVIEW_APPROVED, task, now)

            await audit.record(
                session, actor_id=fresh.id, action=action, entity_type=ENTITY, entity_id=task.id,
                at=now,
                data={"version": submission.version, "stage": str(stage), "final": final,
                      "delegated": delegated, "review_id": review.id,
                      "revision_round": task.revision_round},
            )
        if task.status != old_status:
            await self._sync.on_task_status_changed(task.id, str(old_status), str(task.status))
        return task

    async def _create_output(
        self, session: AsyncSession, task: Task, submission: Submission, owner: User, now: datetime
    ) -> None:
        if await reviews_repo.output_for_task(session, task.id) is not None:
            return
        series = await series_repo.get(session, task.series_id) if task.series_id else None
        output_type = {
            TaskKind.EDIT: OutputType.REEL_VIDEO,
            TaskKind.COVER: OutputType.REEL_COVER,
        }.get(task.kind, OutputType.OTHER)
        search = " ".join(
            part for part in (task.code, task.title, series.name if series else "", owner.full_name) if part
        )
        session.add(
            Output(
                task_id=task.id,
                submission_id=submission.id,
                content_item_id=task.content_item_id,
                output_type=output_type,
                title=task.title,
                series_id=task.series_id,
                owner_id=owner.id,
                approved_at=now,
                search_text=normalize_text(search),
            )
        )

    # ---- done ----------------------------------------------------------------

    async def mark_done(self, actor: User, task_id: int) -> Task:
        """'✅ done' for NONE-chain tasks, or '🏁 done' after upload for APPROVED tasks (v1.2)."""
        now = self._clock.now()
        async with self._db.transaction() as session:
            fresh = await self._fresh(session, actor)
            task = await self._task(session, task_id)
            old_status = task.status
            if old_status == TaskStatus.APPROVED:
                if task.assignee_id != fresh.id and not can_manage_task(fresh, task):
                    raise PermissionDenied("task.done")
            elif task.approval_chain == ApprovalChain.NONE and old_status in (
                TaskStatus.TODO, TaskStatus.IN_PROGRESS
            ):
                if task.assignee_id != fresh.id:
                    raise PermissionDenied("task.done")
                if task.first_submitted_at is None:
                    task.first_submitted_at = now  # counts as delivery for on-time stats
            else:
                raise InvalidTransition(str(old_status), str(TaskStatus.DONE))
            ensure_transition(old_status, TaskStatus.DONE)
            task.status = TaskStatus.DONE
            task.completed_at = now
            await audit.record(
                session, actor_id=fresh.id, action="task.done", entity_type=ENTITY,
                entity_id=task.id, at=now, data={"from": str(old_status)},
            )
            creator = await users_repo.get_by_id(session, task.created_by)
            if creator is not None:
                await self._notify(session, creator, fresh, KIND_TASK_DONE, task, now)
        await self._sync.on_task_status_changed(task.id, str(old_status), str(TaskStatus.DONE))
        return task

    # ---- who reviews ----------------------------------------------------------

    async def _may_review(self, session: AsyncSession, user: User, stage: ReviewStage, now: datetime) -> bool:
        if stage == ReviewStage.L1:
            return has_capability(user, Capability.REVIEW_L1)
        if has_capability(user, Capability.APPROVE_FINAL):
            return True
        return await active_delegate_id(session, now) == user.id

    async def _reviewers(self, session: AsyncSession, stage: ReviewStage, now: datetime) -> list[User]:
        """Who receives the review card. Uses *stored* capabilities so the OWNER is a fallback only."""
        active = list(await users_repo.list_active(session))
        if stage == ReviewStage.L1:
            people = [u for u in active if Capability.REVIEW_L1 in stored_capabilities(u)]
        else:
            delegate_id = await active_delegate_id(session, now)
            if delegate_id is not None:
                people = [u for u in active if u.id == delegate_id]
            else:
                people = [u for u in active if Capability.APPROVE_FINAL in stored_capabilities(u)]
        return people or [u for u in active if is_owner(u)]

    async def _notify_reviewers(
        self, session: AsyncSession, task: Task, submission: Submission, stage: ReviewStage, now: datetime
    ) -> None:
        for reviewer in await self._reviewers(session, stage, now):
            await enqueue(
                session,
                chat_id=reviewer.telegram_id,
                kind=KIND_REVIEW_REQUESTED,
                payload={"task_id": task.id, "user_id": reviewer.id, "submission_id": submission.id,
                         "stage": str(stage)},
                dedupe_key=f"{KIND_REVIEW_REQUESTED}:{submission.id}:{stage}:{reviewer.id}",
                now=now,
                urgent=True,
            )

    async def _notify(
        self, session: AsyncSession, recipient: User, actor: User, kind: str, task: Task,
        now: datetime, extra: dict[str, Any] | None = None,
    ) -> None:
        if recipient.id == actor.id or not recipient.can_use_bot:
            return
        await enqueue(
            session,
            chat_id=recipient.telegram_id,
            kind=kind,
            payload={"task_id": task.id, "user_id": recipient.id, "code": task.code,
                     "title": task.title, **(extra or {})},
            dedupe_key=f"{kind}:{task.id}:{recipient.id}:{now.isoformat()}",
            now=now,
            urgent=True,
        )

    async def _fresh(self, session: AsyncSession, actor: User) -> User:
        fresh = await users_repo.get_by_id(session, actor.id)
        if fresh is None or not fresh.can_use_bot:
            raise PermissionDenied("inactive")
        return fresh

    async def _task(self, session: AsyncSession, task_id: int) -> Task:
        task = await tasks_repo.get(session, task_id)
        if task is None:
            raise NotFound(f"task {task_id}")
        return task
