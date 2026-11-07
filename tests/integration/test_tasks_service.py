"""General tasks at the service level (handoff §3.2, §4.3, §4.6, M1)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from eventum_hq.core.db import Database
from eventum_hq.core.errors import InvalidTransition, NotFound, PermissionDenied, ValidationFailed
from eventum_hq.models import (
    AccessStatus,
    ApprovalChain,
    AuditEvent,
    Notification,
    Role,
    Series,
    Task,
    TaskInput,
    TaskInputKind,
    TaskStatus,
    User,
)
from eventum_hq.services.permissions import ROLE_DEFAULT_CAPABILITIES
from eventum_hq.services.tasks import (
    KIND_TASK_ASSIGNED,
    KIND_TASK_CANCELLED,
    KIND_TASK_DUE_CHANGED,
    KIND_TASK_UNASSIGNED,
    DeadlineState,
    NewTask,
    TaskFilter,
    TaskService,
    deadline_state,
    parse_task_code,
)
from tests.conftest import FakeClock, add_user


class RecordingSync:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def on_task_created(self, task_id: int) -> None:
        self.calls.append(("created", task_id))

    async def on_task_updated(self, task_id: int) -> None:
        self.calls.append(("updated", task_id))

    async def on_task_status_changed(self, task_id: int, old: str, new: str) -> None:
        self.calls.append(("status", task_id, old, new))


@pytest.fixture
def sync() -> RecordingSync:
    return RecordingSync()


@pytest.fixture
def tasks(db: Database, clock: FakeClock, sync: RecordingSync) -> TaskService:
    return TaskService(db, clock, sync)


async def _member(db: Database, tg: int, role: Role, name: str) -> User:
    return await add_user(
        db, telegram_id=tg, role=role, capabilities=list(ROLE_DEFAULT_CAPABILITIES[role]),
        full_name=name,
    )


@pytest.fixture
async def team(db: Database, owner: User) -> dict[str, User]:
    return {
        "barbod": owner,
        "farid": await _member(db, 2001, Role.DIRECTOR, "Farid"),
        "ali": await _member(db, 2002, Role.PROJECT_MANAGER, "Ali"),
        "amin": await _member(db, 2003, Role.CONTENT_SPECIALIST, "Amin"),
        "mohadeseh": await _member(db, 2004, Role.DESIGNER, "Mohadeseh"),
        "sina": await _member(db, 2005, Role.EDITOR, "Sina"),
    }


async def _series_id(db: Database) -> int:
    async with db.transaction() as s:
        series = Series(name="ریل روزانه", kind="REEL", is_active=True)
        s.add(series)
    return series.id


def _new(assignee: User, clock: FakeClock, **kw) -> NewTask:  # type: ignore[no-untyped-def]
    return NewTask(
        title=kw.pop("title", "تامنیل اپیزود ۱۲"),
        assignee_id=assignee.id,
        due_at=kw.pop("due_at", clock.now() + timedelta(days=2)),
        **kw,
    )


async def _all(db: Database, model):  # type: ignore[no-untyped-def]
    async with db.read() as s:
        return (await s.execute(select(model).order_by(model.id))).scalars().all()


async def _notifications(db: Database) -> list[tuple[int, str]]:
    return [(n.chat_id, n.kind) for n in await _all(db, Notification)]


async def _actions(db: Database, task_id: int) -> list[str]:
    return [e.action for e in await _all(db, AuditEvent) if e.entity_type == "task" and e.entity_id == task_id]


# ---- codes -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("T-0042", "T-0042"), ("t42", "T-0042"), ("#T0042", "T-0042"), ("T-۴۲", "T-0042"),
        (" T - 7 ", "T-0007"), ("T-12345", "T-12345"),
        ("R-0001", None), ("hello", None), ("", None), (None, None), ("T-", None),
    ],
)
def test_parse_task_code(text: str | None, code: str | None) -> None:
    assert parse_task_code(text) == code


# ---- create ------------------------------------------------------------------


async def test_farid_creates_task_and_assignee_is_notified(
    db: Database, tasks: TaskService, team, clock: FakeClock, sync: RecordingSync
) -> None:
    series_id = await _series_id(db)
    task = await tasks.create_generic(
        team["farid"],
        _new(team["sina"], clock, description="  توضیح  ", series_id=series_id),
    )
    assert task.code == f"T-{task.id:04d}"
    assert task.status == TaskStatus.TODO
    assert task.approval_chain == ApprovalChain.FINAL  # default
    assert task.description == "توضیح"
    assert task.created_by == team["farid"].id and task.assignee_id == team["sina"].id
    assert await _notifications(db) == [(2005, KIND_TASK_ASSIGNED)]
    assert await _actions(db, task.id) == ["task.created"]
    assert sync.calls == [("created", task.id)]


@pytest.mark.parametrize("person", ["barbod", "farid", "ali"])
async def test_who_can_create(tasks: TaskService, team, clock: FakeClock, person: str) -> None:
    task = await tasks.create_generic(team[person], _new(team["sina"], clock))
    assert task.id


@pytest.mark.parametrize("person", ["amin", "mohadeseh", "sina"])
async def test_who_cannot_create(db: Database, tasks: TaskService, team, clock: FakeClock, person: str) -> None:
    with pytest.raises(PermissionDenied):
        await tasks.create_generic(team[person], _new(team["sina"], clock))
    assert await _all(db, Task) == []


async def test_self_assigned_task_sends_no_notification(db: Database, tasks: TaskService, team, clock) -> None:
    await tasks.create_generic(team["ali"], _new(team["ali"], clock))
    assert await _notifications(db) == []


async def test_brief_files_are_stored_as_task_input(db: Database, tasks: TaskService, team, clock) -> None:
    files = [{"type": "voice", "file_id": "F1", "file_unique_id": "U1", "size": 10,
              "archive_message_id": None}]
    task = await tasks.create_generic(
        team["farid"], _new(team["sina"], clock, description="caption", attachments=files)
    )
    inputs = await _all(db, TaskInput)
    assert len(inputs) == 1
    assert inputs[0].task_id == task.id and inputs[0].kind == TaskInputKind.BRIEF
    assert inputs[0].attachments == files and inputs[0].text == "caption"
    view = await tasks.get_view(team["sina"], task_id=task.id)
    assert view.brief is not None and view.brief.attachments == files


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"title": "   "}, "title_empty"),
        ({"title": "x" * 201}, "title_too_long"),
        ({"description": "x" * 3001}, "description_too_long"),
        ({"series_id": 999}, "series_invalid"),
    ],
)
async def test_create_validation(tasks: TaskService, team, clock, kwargs, code: str) -> None:
    with pytest.raises(ValidationFailed) as info:
        await tasks.create_generic(team["farid"], _new(team["sina"], clock, **kwargs))
    assert info.value.code == code


async def test_cannot_assign_to_inactive_or_pending_user(db: Database, tasks: TaskService, team, clock) -> None:
    pending = await add_user(db, telegram_id=3000, access_status=AccessStatus.PENDING, is_active=False)
    with pytest.raises(ValidationFailed, match="assignee_inactive"):
        await tasks.create_generic(team["farid"], _new(pending, clock))


async def test_naive_due_date_is_rejected(tasks: TaskService, team, clock) -> None:
    with pytest.raises(ValueError):
        await tasks.create_generic(team["farid"], _new(team["sina"], clock, due_at=datetime(2026, 12, 1)))


async def test_codes_are_sequential(tasks: TaskService, team, clock) -> None:
    a = await tasks.create_generic(team["farid"], _new(team["sina"], clock))
    b = await tasks.create_generic(team["farid"], _new(team["sina"], clock))
    assert (a.code, b.code) == ("T-0001", "T-0002")


# ---- view permissions --------------------------------------------------------


@pytest.mark.parametrize(
    ("person", "allowed"),
    [("barbod", True), ("farid", True), ("ali", True), ("sina", True),  # sina = assignee
     ("amin", False), ("mohadeseh", False)],
)
async def test_who_can_view(tasks: TaskService, team, clock, person: str, allowed: bool) -> None:
    task = await tasks.create_generic(team["farid"], _new(team["sina"], clock))
    if allowed:
        view = await tasks.get_view(team[person], code=task.code)
        assert view.task.id == task.id
    else:
        with pytest.raises(PermissionDenied):
            await tasks.get_view(team[person], code=task.code)
        with pytest.raises(PermissionDenied):
            await tasks.history(team[person], task.id)


async def test_view_flags_and_last_event(tasks: TaskService, team, clock) -> None:
    task = await tasks.create_generic(team["farid"], _new(team["sina"], clock))
    as_sina = await tasks.get_view(team["sina"], task_id=task.id)
    assert as_sina.can_start and not as_sina.can_manage
    assert as_sina.last_event is not None and as_sina.last_event.action == "task.created"
    assert as_sina.last_actor is not None and as_sina.last_actor.id == team["farid"].id
    as_farid = await tasks.get_view(team["farid"], task_id=task.id)
    assert as_farid.can_manage and not as_farid.can_start


async def test_unknown_code(tasks: TaskService, team) -> None:
    with pytest.raises(NotFound):
        await tasks.get_view(team["farid"], code="T-9999")
    with pytest.raises(NotFound):
        await tasks.get_view(team["farid"], code="nonsense")


# ---- start / cancel ----------------------------------------------------------


async def test_assignee_starts_task(tasks: TaskService, team, clock, sync: RecordingSync, db) -> None:
    task = await tasks.create_generic(team["farid"], _new(team["sina"], clock))
    started = await tasks.start(team["sina"], task.id)
    assert started.status == TaskStatus.IN_PROGRESS
    assert ("status", task.id, "TODO", "IN_PROGRESS") in sync.calls
    assert await _actions(db, task.id) == ["task.created", "task.started"]
    with pytest.raises(InvalidTransition):
        await tasks.start(team["sina"], task.id)  # already started (stale button)


@pytest.mark.parametrize("person", ["barbod", "farid", "ali", "amin"])
async def test_only_assignee_can_start(tasks: TaskService, team, clock, person: str) -> None:
    task = await tasks.create_generic(team["farid"], _new(team["sina"], clock))
    with pytest.raises(PermissionDenied):
        await tasks.start(team[person], task.id)


@pytest.mark.parametrize("person", ["barbod", "farid", "ali"])
async def test_managers_can_cancel(db: Database, tasks: TaskService, team, clock, person: str) -> None:
    task = await tasks.create_generic(team["farid"], _new(team["sina"], clock))
    cancelled = await tasks.cancel(team[person], task.id)
    assert cancelled.status == TaskStatus.CANCELLED
    assert (2005, KIND_TASK_CANCELLED) in await _notifications(db)
    assert "task.cancelled" in await _actions(db, task.id)
    with pytest.raises(InvalidTransition):
        await tasks.cancel(team[person], task.id)


@pytest.mark.parametrize("person", ["amin", "mohadeseh", "sina"])
async def test_others_cannot_cancel(tasks: TaskService, team, clock, person: str) -> None:
    task = await tasks.create_generic(team["farid"], _new(team["sina"], clock))
    with pytest.raises(PermissionDenied):
        await tasks.cancel(team[person], task.id)


async def test_creator_can_manage_even_without_create_task(db: Database, tasks: TaskService, team, clock) -> None:
    """The creator keeps control if CREATE_TASK is later removed from them."""
    task = await tasks.create_generic(team["ali"], _new(team["sina"], clock))
    async with db.transaction() as s:
        ali = await s.get(User, team["ali"].id)
        ali.capabilities = []
    await tasks.change_due(team["ali"], task.id, clock.now() + timedelta(days=5))


# ---- edit deadline / assignee -------------------------------------------------


async def test_change_due(db: Database, tasks: TaskService, team, clock) -> None:
    task = await tasks.create_generic(team["farid"], _new(team["sina"], clock))
    new_due = clock.now() + timedelta(days=5)
    changed = await tasks.change_due(team["ali"], task.id, new_due)
    assert changed.due_at == new_due
    event = [e for e in await _all(db, AuditEvent) if e.action == "task.due_changed"][0]
    assert event.data["after"] == new_due.isoformat()
    assert event.actor_id == team["ali"].id
    assert (2005, KIND_TASK_DUE_CHANGED) in await _notifications(db)
    with pytest.raises(ValidationFailed, match="same_due"):
        await tasks.change_due(team["ali"], task.id, new_due)


async def test_reassign_notifies_both(db: Database, tasks: TaskService, team, clock) -> None:
    task = await tasks.create_generic(team["farid"], _new(team["sina"], clock))
    moved = await tasks.reassign(team["farid"], task.id, team["mohadeseh"].id)
    assert moved.assignee_id == team["mohadeseh"].id
    notes = await _notifications(db)
    assert (2004, KIND_TASK_ASSIGNED) in notes and (2005, KIND_TASK_UNASSIGNED) in notes
    event = [e for e in await _all(db, AuditEvent) if e.action == "task.reassigned"][0]
    assert event.data == {"before": team["sina"].id, "after": team["mohadeseh"].id}
    with pytest.raises(ValidationFailed, match="same_assignee"):
        await tasks.reassign(team["farid"], task.id, team["mohadeseh"].id)
    # old assignee can no longer see it; new one can
    with pytest.raises(PermissionDenied):
        await tasks.get_view(team["sina"], task_id=task.id)
    assert (await tasks.get_view(team["mohadeseh"], task_id=task.id)).can_start


@pytest.mark.parametrize("person", ["amin", "sina"])
async def test_others_cannot_edit(tasks: TaskService, team, clock, person: str) -> None:
    task = await tasks.create_generic(team["farid"], _new(team["sina"], clock))
    with pytest.raises(PermissionDenied):
        await tasks.change_due(team[person], task.id, clock.now() + timedelta(days=9))
    with pytest.raises(PermissionDenied):
        await tasks.reassign(team[person], task.id, team["amin"].id)


async def test_closed_task_cannot_be_edited(tasks: TaskService, team, clock) -> None:
    task = await tasks.create_generic(team["farid"], _new(team["sina"], clock))
    await tasks.cancel(team["farid"], task.id)
    with pytest.raises(InvalidTransition):
        await tasks.change_due(team["farid"], task.id, clock.now() + timedelta(days=9))
    with pytest.raises(InvalidTransition):
        await tasks.reassign(team["farid"], task.id, team["amin"].id)


# ---- lists and deadlines ------------------------------------------------------


async def test_my_tasks_and_all_tasks_filters(db: Database, tasks: TaskService, team, clock: FakeClock) -> None:
    series_id = await _series_id(db)
    now = clock.now()
    overdue = await tasks.create_generic(team["farid"], _new(team["sina"], clock, due_at=now + timedelta(hours=1)))
    risky = await tasks.create_generic(team["farid"], _new(team["sina"], clock, due_at=now + timedelta(hours=30)))
    later = await tasks.create_generic(
        team["farid"], _new(team["mohadeseh"], clock, due_at=now + timedelta(days=5), series_id=series_id)
    )
    cancelled = await tasks.create_generic(team["farid"], _new(team["sina"], clock))
    await tasks.cancel(team["farid"], cancelled.id)
    clock.advance(hours=8)  # overdue is now 7h late; risky due in 22h

    ids = lambda rows: [r.task.id for r in rows]  # noqa: E731
    assert ids(await tasks.list_my(team["sina"])) == [overdue.id, risky.id]
    assert ids(await tasks.list_all(team["ali"], TaskFilter.OPEN)) == [overdue.id, risky.id, later.id]
    assert ids(await tasks.list_all(team["ali"], TaskFilter.OVERDUE)) == [overdue.id]
    assert ids(await tasks.list_all(team["ali"], TaskFilter.AT_RISK)) == [risky.id]
    assert ids(await tasks.list_all(team["ali"], TaskFilter.BY_USER, team["mohadeseh"].id)) == [later.id]
    assert ids(await tasks.list_all(team["ali"], TaskFilter.BY_SERIES, series_id)) == [later.id]

    rows = await tasks.list_all(team["farid"], TaskFilter.OPEN)
    assert rows[0].assignee.id == team["sina"].id


@pytest.mark.parametrize("person", ["amin", "mohadeseh", "sina"])
async def test_all_tasks_requires_view_all(tasks: TaskService, team, person: str) -> None:
    with pytest.raises(PermissionDenied):
        await tasks.list_all(team[person], TaskFilter.OPEN)


def _task(status=TaskStatus.TODO, due=None, submitted=None) -> Task:  # type: ignore[no-untyped-def]
    return Task(status=status, due_at=due, first_submitted_at=submitted)


NOW = datetime(2026, 11, 7, 8, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("task", "state"),
    [
        (_task(due=None), DeadlineState.NONE),
        (_task(due=NOW - timedelta(minutes=1)), DeadlineState.OVERDUE),
        (_task(due=NOW + timedelta(hours=23)), DeadlineState.AT_RISK),
        (_task(due=NOW + timedelta(hours=25)), DeadlineState.OK),
        # submitted on time → review queue time never counts against the assignee
        (_task(status=TaskStatus.IN_REVIEW, due=NOW - timedelta(days=3),
               submitted=NOW - timedelta(days=4)), DeadlineState.NONE),
        (_task(status=TaskStatus.APPROVED, due=NOW - timedelta(days=3)), DeadlineState.NONE),
        (_task(status=TaskStatus.CANCELLED, due=NOW - timedelta(days=3)), DeadlineState.NONE),
    ],
)
def test_deadline_state(task: Task, state: DeadlineState) -> None:
    assert deadline_state(task, NOW) == state


async def test_history_lists_every_change(tasks: TaskService, team, clock) -> None:
    task = await tasks.create_generic(team["farid"], _new(team["sina"], clock))
    await tasks.start(team["sina"], task.id)
    await tasks.change_due(team["farid"], task.id, clock.now() + timedelta(days=9))
    await tasks.reassign(team["farid"], task.id, team["mohadeseh"].id)
    await tasks.cancel(team["ali"], task.id)
    _task_obj, entries = await tasks.history(team["farid"], task.id)
    assert [e.event.action for e in entries] == [
        "task.created", "task.started", "task.due_changed", "task.reassigned", "task.cancelled",
    ]
    assert entries[1].actor is not None and entries[1].actor.id == team["sina"].id


async def test_deactivated_actor_is_refused(db: Database, tasks: TaskService, team, clock) -> None:
    async with db.transaction() as s:
        farid = await s.get(User, team["farid"].id)
        farid.is_active = False
    with pytest.raises(PermissionDenied):
        await tasks.create_generic(team["farid"], _new(team["sina"], clock))
