"""Reel flow at the service level (handoff §4.5, M3 acceptance)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from eventum_hq.core.db import Database
from eventum_hq.core.errors import InvalidTransition, PermissionDenied, ValidationFailed
from eventum_hq.models import (
    ApprovalChain,
    AuditEvent,
    ContentItem,
    ContentStatus,
    ContentSubtype,
    Notification,
    Output,
    OutputType,
    ReviewStage,
    Role,
    Series,
    Task,
    TaskInputKind,
    TaskKind,
    TaskStatus,
    User,
)
from eventum_hq.services.permissions import ROLE_DEFAULT_CAPABILITIES
from eventum_hq.services.reels import (
    BLOCKED_WAITING_PHOTOS,
    KIND_REEL_CANCELLED,
    KIND_REEL_PHOTOS_READY,
    KIND_REEL_PUBLISHED,
    KIND_REEL_READY,
    KIND_REEL_TASK_APPROVED,
    NewReel,
    ReelService,
    compute_plan,
    parse_reel_code,
)
from eventum_hq.services.reviews import ReviewService
from eventum_hq.services.tasks import DeadlineState, TaskFilter, TaskService, deadline_state
from tests.conftest import OWNER_TG, FakeClock, add_user

FARID, ALI, AMIN, MOHADESEH, SINA = 2001, 2002, 2003, 2004, 2005
VIDEO = {"type": "video", "file_id": "V", "archive_message_id": 11}
PHOTO = {"type": "photo", "file_id": "P", "archive_message_id": 12}


@pytest.fixture
async def team(db: Database, owner: User) -> dict[str, User]:
    people = {"barbod": owner}
    for key, tg, role in [("farid", FARID, Role.DIRECTOR), ("ali", ALI, Role.PROJECT_MANAGER),
                          ("amin", AMIN, Role.CONTENT_SPECIALIST), ("mohadeseh", MOHADESEH, Role.DESIGNER),
                          ("sina", SINA, Role.EDITOR)]:
        people[key] = await add_user(db, telegram_id=tg, role=role, full_name=key.title(),
                                     capabilities=list(ROLE_DEFAULT_CAPABILITIES[role]))
    async with db.transaction() as s:
        s.add_all([Series(name="ریل روزانه", kind="REEL", is_active=True),
                   Series(name="Trial Reels", kind="REEL", is_active=True)])
    return people


@pytest.fixture
def reels(db: Database, clock: FakeClock) -> ReelService:
    return ReelService(db, clock)


@pytest.fixture
def reviews(db: Database, clock: FakeClock) -> ReviewService:
    return ReviewService(db, clock)


@pytest.fixture
def tasks(db: Database, clock: FakeClock) -> TaskService:
    return TaskService(db, clock)


def _new(team, clock: FakeClock, **kw) -> NewReel:  # type: ignore[no-untyped-def]
    return NewReel(
        title=kw.pop("title", "ریل بیت‌کوین"),
        subtype=kw.pop("subtype", ContentSubtype.NORMAL),
        planned_publish_at=kw.pop("publish", clock.now() + timedelta(days=2)),
        timecodes=kw.pop("timecodes", "00:10-00:40"),
        cover_text=kw.pop("cover_text", "بیت‌کوین ۱۰۰ هزار؟"),
        edit_assignee_id=team["sina"].id,
        cover_assignee_id=team["mohadeseh"].id,
        **kw,
    )


async def _all(db: Database, model):  # type: ignore[no-untyped-def]
    async with db.read() as s:
        return list((await s.execute(select(model).order_by(model.id))).scalars())


async def _notes(db: Database) -> list[tuple[int, str]]:
    return [(n.chat_id, n.kind) for n in await _all(db, Notification)]


async def _reel_tasks(db: Database, item_id: int) -> tuple[Task, Task]:
    tasks = [t for t in await _all(db, Task) if t.content_item_id == item_id]
    edit = next(t for t in tasks if t.kind == TaskKind.EDIT)
    cover = next(t for t in tasks if t.kind == TaskKind.COVER)
    return edit, cover


async def _item(db: Database, item_id: int) -> ContentItem:
    async with db.read() as s:
        item = await s.get(ContentItem, item_id)
        assert item is not None
        return item


# ---- plan ------------------------------------------------------------------------

NOW = datetime(2026, 11, 7, 8, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("subtype", "motion", "edit_min"),
    [(ContentSubtype.NORMAL, False, 45), (ContentSubtype.NORMAL, True, 100), (ContentSubtype.TRIAL, True, 30)],
)
def test_plan_defaults(subtype: ContentSubtype, motion: bool, edit_min: int) -> None:
    publish = NOW + timedelta(days=2)
    plan = compute_plan(now=NOW, publish_at=publish, subtype=subtype, motion=motion, offsets={}, estimates={})
    assert plan.edit_due_at == publish - timedelta(hours=6)
    assert plan.cover_due_at == publish - timedelta(hours=6)
    assert plan.photos_due_at == NOW + timedelta(hours=4)
    assert (plan.edit_estimate, plan.cover_estimate) == (edit_min, 45)


def test_photos_due_never_after_edit_due() -> None:
    publish = NOW + timedelta(hours=8)  # edit due = now + 2h < now + 4h
    plan = compute_plan(now=NOW, publish_at=publish, subtype=ContentSubtype.NORMAL, motion=False,
                        offsets={}, estimates={})
    assert plan.photos_due_at == plan.edit_due_at == NOW + timedelta(hours=2)


@pytest.mark.parametrize(("text", "code"), [("R-0001", "R-0001"), ("r1", "R-0001"), ("R-۱۲", "R-0012"),
                                            ("T-0001", None), ("", None)])
def test_parse_reel_code(text: str, code: str | None) -> None:
    assert parse_reel_code(text) == code


# ---- create ------------------------------------------------------------------------


async def test_amin_creates_reel_with_two_tasks(db, reels, team, clock) -> None:
    item = await reels.create(team["amin"], _new(team, clock, motion=True))
    assert item.code == "R-0001" and item.status == ContentStatus.IN_PRODUCTION
    assert item.photos_due_at == clock.now() + timedelta(hours=4)
    edit, cover = await _reel_tasks(db, item.id)
    assert edit.status == TaskStatus.TODO and edit.assignee_id == team["sina"].id
    assert cover.status == TaskStatus.BLOCKED and cover.blocked_reason == BLOCKED_WAITING_PHOTOS
    assert cover.assignee_id == team["mohadeseh"].id
    for task in (edit, cover):
        assert task.approval_chain == ApprovalChain.L1_FINAL and task.created_by == team["amin"].id
        assert task.due_at == item.planned_publish_at - timedelta(hours=6)
    assert (edit.estimated_minutes, cover.estimated_minutes) == (100, 45)
    async with db.read() as s:
        from eventum_hq.models import TaskInput
        inputs = list((await s.execute(select(TaskInput))).scalars())
    assert {(i.task_id, i.kind, i.text) for i in inputs} == {
        (edit.id, TaskInputKind.TIMECODES, "00:10-00:40"),
        (cover.id, TaskInputKind.COVER_TEXT, "بیت‌کوین ۱۰۰ هزار؟"),
    }
    notes = await _notes(db)
    assert (SINA, "task.assigned") in notes and (MOHADESEH, "task.assigned") in notes


@pytest.mark.parametrize("person", ["ali", "mohadeseh", "sina", "farid"])
async def test_only_create_reel_holders(db, reels, team, clock, person) -> None:
    with pytest.raises(PermissionDenied):
        await reels.create(team[person], _new(team, clock))


async def test_owner_can_create_reel(reels, team, clock) -> None:
    assert (await reels.create(team["barbod"], _new(team, clock))).code == "R-0001"


async def test_overrides_and_validation(db, reels, team, clock) -> None:
    custom = clock.now() + timedelta(hours=10)
    item = await reels.create(team["amin"], _new(team, clock, photos_due_at=custom, edit_estimate=60,
                                                  cover_estimate=20))
    edit, cover = await _reel_tasks(db, item.id)
    assert item.photos_due_at == custom and (edit.estimated_minutes, cover.estimated_minutes) == (60, 20)
    with pytest.raises(ValidationFailed, match="photos_after_edit"):
        await reels.create(team["amin"], _new(team, clock, photos_due_at=clock.now() + timedelta(days=5)))
    with pytest.raises(ValidationFailed, match="reel_inputs_missing"):
        await reels.create(team["amin"], _new(team, clock, timecodes="  "))


# ---- cover photos ---------------------------------------------------------------------


async def test_sina_delivers_photos_and_cover_unblocks(db, reels, tasks, team, clock) -> None:
    item = await reels.create(team["amin"], _new(team, clock))
    edit, cover = await _reel_tasks(db, item.id)
    assert (await tasks.get_view(team["sina"], task_id=edit.id)).can_send_photos
    with pytest.raises(PermissionDenied):
        await reels.deliver_cover_photos(team["mohadeseh"], edit.id, [PHOTO])
    clock.advance(hours=1)
    await reels.deliver_cover_photos(team["sina"], edit.id, [PHOTO, PHOTO])
    _, cover = await _reel_tasks(db, item.id)
    assert cover.status == TaskStatus.TODO and cover.blocked_reason is None
    stored = await _item(db, item.id)
    assert stored.photos_delivered_at == clock.now() and stored.photos_late is False
    assert (MOHADESEH, KIND_REEL_PHOTOS_READY) in await _notes(db)
    view = await tasks.get_view(team["mohadeseh"], task_id=cover.id)
    kinds = [i.kind for i in view.inputs]
    assert TaskInputKind.COVER_TEXT in kinds and TaskInputKind.COVER_PHOTOS in kinds
    assert not (await tasks.get_view(team["sina"], task_id=edit.id)).can_send_photos
    with pytest.raises(InvalidTransition):  # already delivered
        await reels.deliver_cover_photos(team["sina"], edit.id, [PHOTO])


async def test_late_photos_are_sinas_delay(db, reels, team, clock) -> None:
    item = await reels.create(team["amin"], _new(team, clock))
    edit, _ = await _reel_tasks(db, item.id)
    clock.advance(hours=5)  # photos were due after 4h
    await reels.deliver_cover_photos(team["sina"], edit.id, [PHOTO])
    assert (await _item(db, item.id)).photos_late is True


async def test_blocked_cover_is_at_risk_but_never_overdue(db, reels, tasks, team, clock) -> None:
    item = await reels.create(team["amin"], _new(team, clock, publish=clock.now() + timedelta(hours=20)))
    _, cover = await _reel_tasks(db, item.id)
    assert deadline_state(cover, clock.now()) == DeadlineState.AT_RISK
    clock.advance(days=2)  # way past the cover deadline, still waiting for photos
    _, cover = await _reel_tasks(db, item.id)
    assert deadline_state(cover, clock.now()) == DeadlineState.AT_RISK
    overdue = [r.task.id for r in await tasks.list_all(team["ali"], TaskFilter.OVERDUE)]
    at_risk = [r.task.id for r in await tasks.list_all(team["ali"], TaskFilter.AT_RISK)]
    assert cover.id not in overdue and cover.id in at_risk


# ---- review → ready → publish ------------------------------------------------------------


async def _approve_task(reviews: ReviewService, team, task: Task, assignee: str) -> None:
    sub = await reviews.submit(team[assignee], task.id, attachments=[VIDEO], links=[], note=None)
    await reviews.approve(team["amin"], sub.id, 1, ReviewStage.L1)
    await reviews.approve(team["farid"], sub.id, 1, ReviewStage.FINAL)


async def test_full_reel_from_creation_to_publish(db, reels, reviews, team, clock) -> None:
    """M3 acceptance: a reel goes from creation to publication."""
    item = await reels.create(team["amin"], _new(team, clock))
    edit, cover = await _reel_tasks(db, item.id)

    await _approve_task(reviews, team, edit, "sina")
    edit, _ = await _reel_tasks(db, item.id)
    assert edit.status == TaskStatus.DONE  # reel tasks finish on final approval (v1.2)
    assert (AMIN, KIND_REEL_TASK_APPROVED) in await _notes(db)
    assert (await _item(db, item.id)).status == ContentStatus.IN_PRODUCTION  # cover not yet

    await reels.deliver_cover_photos(team["sina"], edit.id, [PHOTO])
    await _approve_task(reviews, team, cover, "mohadeseh")
    assert (await _item(db, item.id)).status == ContentStatus.READY_TO_PUBLISH
    assert (OWNER_TG, KIND_REEL_READY) in await _notes(db)  # Barbod has PUBLISH
    outputs = await _all(db, Output)
    assert sorted(o.output_type for o in outputs) == [OutputType.REEL_COVER, OutputType.REEL_VIDEO]
    assert all(o.content_item_id == item.id for o in outputs)
    assert len(await reels.final_files(item.id)) == 2
    ready = await reels.ready_list(team["barbod"])
    assert [v.item.id for v in ready] == [item.id] and ready[0].can_publish

    with pytest.raises(PermissionDenied):
        await reels.publish(team["amin"], item.id, ["https://instagram.com/p/x"])
    with pytest.raises(ValidationFailed, match="links_invalid"):
        await reels.publish(team["barbod"], item.id, ["not a link"])
    published = await reels.publish(team["barbod"], item.id,
                                    ["https://instagram.com/p/x", "https://youtube.com/shorts/y"])
    assert published.status == ContentStatus.PUBLISHED and published.published_at == clock.now()
    assert published.publish_links == ["https://instagram.com/p/x", "https://youtube.com/shorts/y"]
    assert (AMIN, KIND_REEL_PUBLISHED) in await _notes(db)
    with pytest.raises(InvalidTransition):
        await reels.publish(team["barbod"], item.id, ["https://t.me/x"])
    actions = [e.action for e in await _all(db, AuditEvent) if e.entity_type == "content_item"]
    assert actions == ["reel.created", "reel.photos_delivered", "reel.ready", "reel.published"]


async def test_ready_only_when_both_done(db, reels, reviews, team, clock) -> None:
    item = await reels.create(team["amin"], _new(team, clock))
    edit, cover = await _reel_tasks(db, item.id)
    await reels.deliver_cover_photos(team["sina"], edit.id, [PHOTO])
    await _approve_task(reviews, team, cover, "mohadeseh")
    assert (await _item(db, item.id)).status == ContentStatus.IN_PRODUCTION
    with pytest.raises(PermissionDenied):
        await reels.ready_list(team["amin"])


# ---- cancel ------------------------------------------------------------------------------


@pytest.mark.parametrize("person", ["amin", "farid", "barbod"])
async def test_cancel_reel(db, reels, team, clock, person) -> None:
    item = await reels.create(team["amin"], _new(team, clock))
    cancelled = await reels.cancel(team[person], item.id)
    assert cancelled.status == ContentStatus.CANCELLED
    edit, cover = await _reel_tasks(db, item.id)
    assert edit.status == cover.status == TaskStatus.CANCELLED
    notes = await _notes(db)
    assert (SINA, KIND_REEL_CANCELLED) in notes and (MOHADESEH, KIND_REEL_CANCELLED) in notes
    with pytest.raises(InvalidTransition):
        await reels.cancel(team[person], item.id)


@pytest.mark.parametrize("person", ["ali", "sina", "mohadeseh"])
async def test_others_cannot_cancel_reel(reels, team, clock, person) -> None:
    item = await reels.create(team["amin"], _new(team, clock))
    with pytest.raises(PermissionDenied):
        await reels.cancel(team[person], item.id)


async def test_reel_tasks_are_not_cancelled_one_by_one(db, reels, tasks, team, clock) -> None:
    item = await reels.create(team["amin"], _new(team, clock))
    edit, _ = await _reel_tasks(db, item.id)
    with pytest.raises(ValidationFailed, match="reel_task_cancel"):
        await tasks.cancel(team["amin"], edit.id)


async def test_reel_view_permissions(reels, team, clock) -> None:
    item = await reels.create(team["amin"], _new(team, clock))
    for person in ("amin", "sina", "mohadeseh", "farid", "ali", "barbod"):
        view = await reels.view(team[person], code=item.code)
        assert view.item.id == item.id
    assert (await reels.view(team["amin"], item_id=item.id)).can_cancel
    assert not (await reels.view(team["sina"], item_id=item.id)).can_cancel
