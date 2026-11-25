"""Delivery, review chains, revisions, delegation, outputs and DONE (handoff §4.4, §4.7, §4.8, v1.2)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from eventum_hq.core.db import Database
from eventum_hq.core.errors import (
    AlreadyDecided,
    InvalidTransition,
    PermissionDenied,
    ValidationFailed,
)
from eventum_hq.models import (
    ApprovalChain,
    AuditEvent,
    Notification,
    Output,
    OutputType,
    Review,
    ReviewStage,
    Role,
    Setting,
    Task,
    TaskStatus,
    User,
)
from eventum_hq.services.delegations import DelegationService
from eventum_hq.services.permissions import ROLE_DEFAULT_CAPABILITIES
from eventum_hq.services.reviews import (
    KIND_REVIEW_APPROVED,
    KIND_REVIEW_CHANGES,
    KIND_REVIEW_L1_APPROVED,
    KIND_REVIEW_REQUESTED,
    KIND_TASK_DONE,
    ReviewService,
)
from eventum_hq.services.tasks import NewTask, TaskService
from tests.conftest import OWNER_TG, FakeClock, add_user

FILE = {"type": "video", "file_id": "F1", "file_unique_id": "U1", "size": 50_000_000,
        "archive_message_id": 77}
FARID, ALI, AMIN, SINA = 2001, 2002, 2003, 2005


@pytest.fixture
def tasks(db: Database, clock: FakeClock) -> TaskService:
    return TaskService(db, clock)


@pytest.fixture
def reviews(db: Database, clock: FakeClock) -> ReviewService:
    return ReviewService(db, clock)


@pytest.fixture
def delegations(db: Database, clock: FakeClock) -> DelegationService:
    return DelegationService(db, clock)


@pytest.fixture
async def team(db: Database, owner: User) -> dict[str, User]:
    people = {"barbod": owner}
    for key, tg, role in [("farid", FARID, Role.DIRECTOR), ("ali", ALI, Role.PROJECT_MANAGER),
                          ("amin", AMIN, Role.CONTENT_SPECIALIST), ("sina", SINA, Role.EDITOR)]:
        people[key] = await add_user(db, telegram_id=tg, role=role, full_name=key.title(),
                                     capabilities=list(ROLE_DEFAULT_CAPABILITIES[role]))
    return people


async def _task(tasks: TaskService, team, clock: FakeClock, chain: ApprovalChain) -> Task:
    return await tasks.create_generic(
        team["farid"],
        NewTask(title="تامنیل", assignee_id=team["sina"].id, due_at=clock.now() + timedelta(days=1),
                approval_chain=chain),
    )


async def _reload(db: Database, task_id: int) -> Task:
    async with db.read() as s:
        task = await s.get(Task, task_id)
        assert task is not None
        return task


async def _all(db: Database, model):  # type: ignore[no-untyped-def]
    async with db.read() as s:
        return list((await s.execute(select(model).order_by(model.id))).scalars())


async def _notes(db: Database) -> list[tuple[int, str]]:
    return [(n.chat_id, n.kind) for n in await _all(db, Notification)]


async def _submit(reviews: ReviewService, team, task: Task, **kw):  # type: ignore[no-untyped-def]
    return await reviews.submit(team["sina"], task.id, attachments=kw.get("files", [FILE]),
                                links=kw.get("links", []), note=kw.get("note"))


# ---- delivery ------------------------------------------------------------------


async def test_submit_creates_version_and_notifies_farid(db, tasks, reviews, team, clock) -> None:
    task = await _task(tasks, team, clock, ApprovalChain.FINAL)
    clock.advance(hours=2)
    sub = await _submit(reviews, team, task, note=" اولین نسخه ", links=["https://youtu.be/x"])
    assert sub.version == 1 and sub.note == "اولین نسخه" and sub.links == ["https://youtu.be/x"]
    task = await _reload(db, task.id)
    assert task.status == TaskStatus.IN_REVIEW and task.review_stage == ReviewStage.FINAL
    assert task.first_submitted_at == clock.now()
    assert (FARID, KIND_REVIEW_REQUESTED) in await _notes(db)
    assert (OWNER_TG, KIND_REVIEW_REQUESTED) not in await _notes(db)  # Barbod is not a reviewer


async def test_l1_chain_goes_to_amin_first(db, tasks, reviews, team, clock) -> None:
    task = await _task(tasks, team, clock, ApprovalChain.L1_FINAL)
    await _submit(reviews, team, task)
    assert (await _reload(db, task.id)).review_stage == ReviewStage.L1
    notes = await _notes(db)
    assert (AMIN, KIND_REVIEW_REQUESTED) in notes and (FARID, KIND_REVIEW_REQUESTED) not in notes


@pytest.mark.parametrize("person", ["farid", "ali", "amin", "barbod"])
async def test_only_assignee_can_submit(tasks, reviews, team, clock, person) -> None:
    task = await _task(tasks, team, clock, ApprovalChain.FINAL)
    with pytest.raises(PermissionDenied):
        await reviews.submit(team[person], task.id, attachments=[FILE], links=[], note=None)


async def test_empty_submission_is_rejected(tasks, reviews, team, clock) -> None:
    task = await _task(tasks, team, clock, ApprovalChain.FINAL)
    with pytest.raises(ValidationFailed, match="submission_empty"):
        await _submit(reviews, team, task, files=[], links=[])


async def test_none_chain_is_normalized_to_final(tasks, reviews, team, clock) -> None:
    task = await _task(tasks, team, clock, ApprovalChain.NONE)
    assert task.approval_chain == ApprovalChain.FINAL
    await _submit(reviews, team, task)


async def test_cannot_submit_while_in_review(tasks, reviews, team, clock) -> None:
    task = await _task(tasks, team, clock, ApprovalChain.FINAL)
    await _submit(reviews, team, task)
    with pytest.raises(InvalidTransition):
        await _submit(reviews, team, task)


# ---- FINAL chain -----------------------------------------------------------------


async def test_final_chain_full_scenario_with_revision(db, tasks, reviews, team, clock) -> None:
    """M2 acceptance: submit → changes → v2 → approve → Output; then 🏁 done."""
    task = await _task(tasks, team, clock, ApprovalChain.FINAL)
    v1 = await _submit(reviews, team, task)
    await reviews.request_changes(team["farid"], v1.id, 1, ReviewStage.FINAL,
                                  note_text="رنگ را عوض کن", note_attachments=[])
    t = await _reload(db, task.id)
    assert t.status == TaskStatus.CHANGES_REQUESTED and t.revision_round == 1
    assert (SINA, KIND_REVIEW_CHANGES) in await _notes(db)

    v2 = await _submit(reviews, team, task)
    assert v2.version == 2
    t = await _reload(db, task.id)
    assert t.review_stage == ReviewStage.FINAL

    approved = await reviews.approve(team["farid"], v2.id, 2, ReviewStage.FINAL)
    assert approved.status == TaskStatus.APPROVED and approved.review_stage is None
    assert (SINA, KIND_REVIEW_APPROVED) in await _notes(db)
    outputs = await _all(db, Output)
    assert len(outputs) == 1
    out = outputs[0]
    assert out.task_id == task.id and out.submission_id == v2.id
    assert out.output_type == OutputType.OTHER and out.owner_id == team["sina"].id
    assert "t-0001" in out.search_text and "تامنیل" in out.search_text

    done = await reviews.mark_done(team["sina"], task.id)
    assert done.status == TaskStatus.DONE and done.completed_at == clock.now()
    assert (FARID, KIND_TASK_DONE) in await _notes(db)
    actions = [e.action for e in await _all(db, AuditEvent) if e.entity_type == "task"]
    assert actions == ["task.created", "task.submitted", "review.changes_requested",
                       "task.submitted", "review.approved", "task.done"]


@pytest.mark.parametrize("person", ["ali", "amin", "sina"])
async def test_only_final_reviewers_can_approve_final(tasks, reviews, team, clock, person) -> None:
    task = await _task(tasks, team, clock, ApprovalChain.FINAL)
    sub = await _submit(reviews, team, task)
    with pytest.raises(PermissionDenied):
        await reviews.approve(team[person], sub.id, 1, ReviewStage.FINAL)


async def test_owner_cannot_step_in_on_final(tasks, reviews, team, clock) -> None:
    task = await _task(tasks, team, clock, ApprovalChain.FINAL)
    sub = await _submit(reviews, team, task)
    with pytest.raises(PermissionDenied):
        await reviews.approve(team["barbod"], sub.id, 1, ReviewStage.FINAL)


async def test_changes_need_a_note(tasks, reviews, team, clock) -> None:
    task = await _task(tasks, team, clock, ApprovalChain.FINAL)
    sub = await _submit(reviews, team, task)
    with pytest.raises(ValidationFailed, match="notes_empty"):
        await reviews.request_changes(team["farid"], sub.id, 1, ReviewStage.FINAL,
                                      note_text="  ", note_attachments=[])


# ---- L1_FINAL chain ----------------------------------------------------------------


async def test_l1_then_final(db, tasks, reviews, team, clock) -> None:
    task = await _task(tasks, team, clock, ApprovalChain.L1_FINAL)
    sub = await _submit(reviews, team, task)
    with pytest.raises(PermissionDenied):
        await reviews.approve(team["farid"], sub.id, 1, ReviewStage.L1)  # Farid has no REVIEW_L1
    t = await reviews.approve(team["amin"], sub.id, 1, ReviewStage.L1)
    assert t.status == TaskStatus.IN_REVIEW and t.review_stage == ReviewStage.FINAL
    notes = await _notes(db)
    assert (FARID, KIND_REVIEW_REQUESTED) in notes and (SINA, KIND_REVIEW_L1_APPROVED) in notes
    assert await _all(db, Output) == []
    t = await reviews.approve(team["farid"], sub.id, 1, ReviewStage.FINAL)
    assert t.status == TaskStatus.APPROVED
    stages = [(r.stage, r.delegated) for r in await _all(db, Review)]
    assert stages == [(ReviewStage.L1, False), (ReviewStage.FINAL, False)]


async def test_revision_from_final_returns_to_final(db, tasks, reviews, team, clock) -> None:
    task = await _task(tasks, team, clock, ApprovalChain.L1_FINAL)
    sub = await _submit(reviews, team, task)
    await reviews.approve(team["amin"], sub.id, 1, ReviewStage.L1)
    await reviews.request_changes(team["farid"], sub.id, 1, ReviewStage.FINAL, note_text="x",
                                  note_attachments=[])
    await _submit(reviews, team, task)
    assert (await _reload(db, task.id)).review_stage == ReviewStage.FINAL  # skips Amin


async def test_revision_from_l1_returns_to_l1(db, tasks, reviews, team, clock) -> None:
    task = await _task(tasks, team, clock, ApprovalChain.L1_FINAL)
    sub = await _submit(reviews, team, task)
    await reviews.request_changes(team["amin"], sub.id, 1, ReviewStage.L1, note_text="x",
                                  note_attachments=[{"type": "voice", "file_id": "V"}])
    await _submit(reviews, team, task)
    assert (await _reload(db, task.id)).review_stage == ReviewStage.L1


async def test_revision_setting_off_restarts_chain(db, tasks, reviews, team, clock) -> None:
    async with db.transaction() as s:
        s.add(Setting(key="revision_returns_to_requesting_stage", value=False))
    task = await _task(tasks, team, clock, ApprovalChain.L1_FINAL)
    sub = await _submit(reviews, team, task)
    await reviews.approve(team["amin"], sub.id, 1, ReviewStage.L1)
    await reviews.request_changes(team["farid"], sub.id, 1, ReviewStage.FINAL, note_text="x",
                                  note_attachments=[])
    await _submit(reviews, team, task)
    assert (await _reload(db, task.id)).review_stage == ReviewStage.L1


# ---- concurrency lock ---------------------------------------------------------------


async def test_stale_card_is_refused(db, tasks, reviews, team, clock) -> None:
    task = await _task(tasks, team, clock, ApprovalChain.L1_FINAL)
    v1 = await _submit(reviews, team, task)
    await reviews.request_changes(team["amin"], v1.id, 1, ReviewStage.L1, note_text="x",
                                  note_attachments=[])
    await _submit(reviews, team, task)
    with pytest.raises(AlreadyDecided):  # old v1 card
        await reviews.approve(team["amin"], v1.id, 1, ReviewStage.L1)


async def test_double_decision_is_refused(tasks, reviews, team, clock) -> None:
    task = await _task(tasks, team, clock, ApprovalChain.L1_FINAL)
    sub = await _submit(reviews, team, task)
    await reviews.approve(team["amin"], sub.id, 1, ReviewStage.L1)
    with pytest.raises(AlreadyDecided):  # L1 card pressed again after moving to FINAL
        await reviews.approve(team["amin"], sub.id, 1, ReviewStage.L1)
    await reviews.approve(team["farid"], sub.id, 1, ReviewStage.FINAL)
    with pytest.raises(AlreadyDecided):
        await reviews.approve(team["farid"], sub.id, 1, ReviewStage.FINAL)


async def test_forged_version_is_refused(tasks, reviews, team, clock) -> None:
    task = await _task(tasks, team, clock, ApprovalChain.FINAL)
    sub = await _submit(reviews, team, task)
    with pytest.raises(AlreadyDecided):
        await reviews.approve(team["farid"], sub.id, 9, ReviewStage.FINAL)


# ---- delegation (F7) ----------------------------------------------------------------


async def _delegate(delegations: DelegationService, team, clock, hours: int = 48):  # type: ignore[no-untyped-def]
    return await delegations.create(team["farid"], team["amin"].id, clock.now() + timedelta(hours=hours))


async def test_delegation_cannot_skip_final(db, tasks, reviews, delegations, team, clock) -> None:
    await _delegate(delegations, team, clock)
    task = await _task(tasks, team, clock, ApprovalChain.L1_FINAL)
    sub = await _submit(reviews, team, task)
    t = await reviews.approve(team["amin"], sub.id, 1, ReviewStage.L1)
    assert t.status == TaskStatus.IN_REVIEW and t.review_stage == ReviewStage.FINAL
    review = (await _all(db, Review))[-1]
    assert review.delegated is False
    assert (FARID, KIND_REVIEW_REQUESTED) in await _notes(db)
    assert await _all(db, Output) == []


async def test_delegation_cannot_reroute_final(db, tasks, reviews, delegations, team, clock) -> None:
    await _delegate(delegations, team, clock)
    task = await _task(tasks, team, clock, ApprovalChain.FINAL)
    sub = await _submit(reviews, team, task)
    notes = await _notes(db)
    assert (AMIN, KIND_REVIEW_REQUESTED) not in notes and (FARID, KIND_REVIEW_REQUESTED) in notes
    with pytest.raises(PermissionDenied):
        await reviews.approve(team["amin"], sub.id, 1, ReviewStage.FINAL)


async def test_expired_delegation_has_no_effect(db, tasks, reviews, delegations, team, clock) -> None:
    await _delegate(delegations, team, clock, hours=1)
    clock.advance(hours=2)
    task = await _task(tasks, team, clock, ApprovalChain.FINAL)
    sub = await _submit(reviews, team, task)
    assert (FARID, KIND_REVIEW_REQUESTED) in await _notes(db)
    with pytest.raises(PermissionDenied):
        await reviews.approve(team["amin"], sub.id, 1, ReviewStage.FINAL)


async def test_revoked_delegation_has_no_effect(db, tasks, reviews, delegations, team, clock) -> None:
    d = await _delegate(delegations, team, clock)
    await delegations.revoke(team["farid"], d.id)
    assert await delegations.current() is None
    task = await _task(tasks, team, clock, ApprovalChain.L1_FINAL)
    sub = await _submit(reviews, team, task)
    t = await reviews.approve(team["amin"], sub.id, 1, ReviewStage.L1)
    assert t.review_stage == ReviewStage.FINAL  # normal chain again
    with pytest.raises(AlreadyDecided):
        await delegations.revoke(team["farid"], d.id)


async def test_delegation_rules(db, delegations, team, clock) -> None:
    for person in ("ali", "amin", "sina"):
        with pytest.raises(PermissionDenied):
            await delegations.create(team[person], team["amin"].id, clock.now() + timedelta(days=1))
    with pytest.raises(ValidationFailed, match="delegate_invalid"):  # Sina has no REVIEW_L1
        await delegations.create(team["farid"], team["sina"].id, clock.now() + timedelta(days=1))
    with pytest.raises(ValidationFailed, match="delegation_end_past"):
        await delegations.create(team["farid"], team["amin"].id, clock.now() - timedelta(minutes=1))
    d = await _delegate(delegations, team, clock)
    notes = await _notes(db)
    assert (FARID, "delegation.started") in notes and (AMIN, "delegation.started") in notes
    assert await delegations.is_active_delegate(team["amin"].id)
    assert [u.id for u in await delegations.candidates()] == [team["amin"].id]
    # a new delegation replaces the old one
    d2 = await _delegate(delegations, team, clock, hours=5)
    current = await delegations.current()
    assert current is not None and current.delegation.id == d2.id != d.id


# ---- done ----------------------------------------------------------------------------


async def test_none_chain_done(db, tasks, reviews, team, clock) -> None:
    task = await _task(tasks, team, clock, ApprovalChain.NONE)
    with pytest.raises(InvalidTransition):
        await reviews.mark_done(team["farid"], task.id)
    assert await _all(db, Output) == []
    with pytest.raises(InvalidTransition):
        await reviews.mark_done(team["sina"], task.id)


async def test_done_not_allowed_before_approval(tasks, reviews, team, clock) -> None:
    task = await _task(tasks, team, clock, ApprovalChain.FINAL)
    with pytest.raises(InvalidTransition):
        await reviews.mark_done(team["sina"], task.id)


async def test_manager_can_finish_approved_task(tasks, reviews, team, clock) -> None:
    task = await _task(tasks, team, clock, ApprovalChain.FINAL)
    sub = await _submit(reviews, team, task)
    await reviews.approve(team["farid"], sub.id, 1, ReviewStage.FINAL)
    with pytest.raises(PermissionDenied):
        await reviews.mark_done(team["amin"], task.id)
    assert (await reviews.mark_done(team["ali"], task.id)).status == TaskStatus.DONE


async def test_task_view_buttons(tasks, reviews, team, clock) -> None:
    task = await _task(tasks, team, clock, ApprovalChain.FINAL)
    view = await tasks.get_view(team["sina"], task_id=task.id)
    assert view.can_submit and not view.can_mark_done and not view.can_finish
    sub = await _submit(reviews, team, task)
    view = await tasks.get_view(team["sina"], task_id=task.id)
    assert not view.can_submit and view.latest_version == 1
    await reviews.approve(team["farid"], sub.id, 1, ReviewStage.FINAL)
    view = await tasks.get_view(team["sina"], task_id=task.id)
    assert view.can_finish and not view.can_submit
    none_task = await _task(tasks, team, clock, ApprovalChain.NONE)
    view = await tasks.get_view(team["sina"], task_id=none_task.id)
    assert not view.can_mark_done and view.can_submit


async def test_review_queues(tasks, reviews, delegations, team, clock) -> None:
    a = await _task(tasks, team, clock, ApprovalChain.L1_FINAL)
    b = await _task(tasks, team, clock, ApprovalChain.FINAL)
    await _submit(reviews, team, a)
    await _submit(reviews, team, b)
    assert [r.task.id for r in await reviews.queue(team["amin"], ReviewStage.L1)] == [a.id]
    assert [r.task.id for r in await reviews.queue(team["farid"], ReviewStage.FINAL)] == [b.id]
    with pytest.raises(PermissionDenied):
        await reviews.queue(team["amin"], ReviewStage.FINAL)
    await _delegate(delegations, team, clock)
    with pytest.raises(PermissionDenied):
        await reviews.queue(team["amin"], ReviewStage.FINAL)
    with pytest.raises(PermissionDenied):
        await reviews.queue(team["sina"], ReviewStage.L1)


async def test_on_time_uses_first_submission_only(db, tasks, reviews, team, clock) -> None:
    """Review queue time never counts as the assignee's delay (§4.7)."""
    task = await _task(tasks, team, clock, ApprovalChain.FINAL)  # due in 24h
    clock.advance(hours=20)
    sub = await _submit(reviews, team, task)
    clock.advance(days=3)  # Farid takes 3 days
    await reviews.request_changes(team["farid"], sub.id, 1, ReviewStage.FINAL, note_text="x",
                                  note_attachments=[])
    await _submit(reviews, team, task)
    t = await _reload(db, task.id)
    assert t.first_submitted_at is not None and t.due_at is not None
    assert t.first_submitted_at <= t.due_at


async def test_missing_founder_keeps_submission_pending_without_owner_fallback(db, tasks, reviews, team, clock):
    task = await _task(tasks, team, clock, ApprovalChain.FINAL)
    async with db.transaction() as session:
        founder = await session.get(User, team["farid"].id)
        founder.is_active = False
    sub = await _submit(reviews, team, task)
    assert not [n for n in await _all(db, Notification) if n.kind == KIND_REVIEW_REQUESTED]
    for person in ("farid", "barbod", "amin"):
        with pytest.raises(PermissionDenied):
            await reviews.approve(team[person], sub.id, 1, ReviewStage.FINAL)
    assert (await _reload(db, task.id)).status == TaskStatus.IN_REVIEW
    assert await _all(db, Output) == []
    async with db.transaction() as session:
        founder = await session.get(User, team["farid"].id)
        founder.is_active = True
    assert [r.task.id for r in await reviews.queue(team["farid"], ReviewStage.FINAL)] == [task.id]
    await reviews.approve(team["farid"], sub.id, 1, ReviewStage.FINAL)


async def test_legacy_none_task_requires_founder(db, tasks, reviews, team, clock):
    task = await _task(tasks, team, clock, ApprovalChain.FINAL)
    async with db.transaction() as session:
        legacy = await session.get(Task, task.id)
        legacy.approval_chain = ApprovalChain.NONE
    with pytest.raises(InvalidTransition):
        await reviews.mark_done(team["sina"], task.id)
    sub = await _submit(reviews, team, task)
    assert (await _reload(db, task.id)).review_stage == ReviewStage.FINAL
    assert (FARID, KIND_REVIEW_REQUESTED) in await _notes(db)
    await reviews.approve(team["farid"], sub.id, sub.version, ReviewStage.FINAL)
