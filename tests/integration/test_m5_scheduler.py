"""M5: the tick — reminders, overdue, quiet hours, recurrences, reports, backups, heartbeat.

The clock starts on Saturday 1405/08/16 (2026-11-07); Saturday is weekday 0.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

from eventum_hq.bot import texts
from eventum_hq.bot.outbox import OutboxSender
from eventum_hq.core.db import Database
from eventum_hq.core.errors import PermissionDenied, ValidationFailed
from eventum_hq.core.jalali import tehran_to_utc
from eventum_hq.models import (
    ApprovalChain,
    Recurrence,
    Notification,
    NotificationStatus,
    RecurrenceRule,
    ReviewStage,
    Role,
    Setting,
    Task,
    TaskStatus,
    User,
)
from eventum_hq.scheduler.tick import Scheduler
from eventum_hq.services import deadlines as dl
from eventum_hq.services import periodic as pj
from eventum_hq.services.backup import KEEP, BackupService, backup_name
from eventum_hq.services.notifications import OutboxStore, enqueue
from eventum_hq.services.permissions import ROLE_DEFAULT_CAPABILITIES
from eventum_hq.services.recurrences import NewRecurrence, RecurrenceService
from eventum_hq.services.reports import ReportService
from eventum_hq.services.tasks import NewTask, TaskService
from eventum_hq.services.users import UserService
from tests.conftest import OWNER_TG, FakeClock, add_user

FARID, SINA = 2001, 2005
GROUP = -100777
SAT = date(2026, 11, 7)


def at(hh: int, mm: int = 0, day: date = SAT) -> datetime:
    return tehran_to_utc(day, time(hh, mm))


class FakeSender:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []
        self.documents: list[tuple[int, Any, str]] = []

    async def send_message(self, chat_id: int, text: str, **kwargs: Any) -> None:
        self.sent.append((chat_id, text))

    async def send_document(self, chat_id: int, document: Any, **kwargs: Any) -> None:
        self.documents.append((chat_id, document, kwargs.get("caption", "")))


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(at(9, 30))


@pytest.fixture
async def people(db: Database, owner: User) -> dict[str, User]:
    farid = await add_user(db, telegram_id=FARID, role=Role.DIRECTOR, full_name="Farid",
                           capabilities=list(ROLE_DEFAULT_CAPABILITIES[Role.DIRECTOR]))
    sina = await add_user(db, telegram_id=SINA, role=Role.EDITOR, full_name="Sina")
    return {"owner": owner, "farid": farid, "sina": sina}


async def _task(db: Database, clock: FakeClock, actor: User, assignee: User, due: datetime,
                minutes: int | None = None, title: str = "کار") -> Task:
    return await TaskService(db, clock).create_generic(
        actor, NewTask(title=title, assignee_id=assignee.id, due_at=due, estimated_minutes=minutes))


async def _rows(db: Database, kind: str | None = None) -> list[Notification]:
    async with db.read() as s:
        query = select(Notification).order_by(Notification.id)
        if kind is not None:
            query = query.where(Notification.kind == kind)
        return list((await s.execute(query)).scalars())


async def _update_task(db: Database, task_id: int, **values: Any) -> None:
    async with db.transaction() as s:
        task = await s.get(Task, task_id)
        assert task is not None
        for key, value in values.items():
            setattr(task, key, value)


# ---- reminders and overdue ---------------------------------------------------------


async def test_day_reminder_once_after_10(db: Database, clock: FakeClock, people) -> None:
    deadlines = dl.DeadlineService(db, clock)
    today = await _task(db, clock, people["owner"], people["sina"], at(18))
    await _task(db, clock, people["owner"], people["sina"], at(18, day=SAT + timedelta(days=1)))
    await deadlines.run()
    assert await _rows(db, dl.KIND_REMINDER_DAY) == []
    clock._now = at(10, 1)
    await deadlines.run()
    rows = await _rows(db, dl.KIND_REMINDER_DAY)
    assert [(r.chat_id, r.payload["task_id"]) for r in rows] == [(SINA, today.id)]
    clock.advance(minutes=5)
    await deadlines.run()
    assert len(await _rows(db, dl.KIND_REMINDER_DAY)) == 1


async def test_soon_reminder_only_in_its_window(db: Database, clock: FakeClock, people) -> None:
    deadlines = dl.DeadlineService(db, clock)
    task = await _task(db, clock, people["owner"], people["sina"], at(18))
    clock._now = at(16, 0)
    await deadlines.run()
    clock._now = at(16, 10)
    await deadlines.run()
    assert [r.payload["task_id"] for r in await _rows(db, dl.KIND_REMINDER_SOON)] == [task.id]
    clock._now = at(16, 50)  # assigned 40 minutes before its deadline: no reminder right away
    late = await _task(db, clock, people["owner"], people["sina"], at(17, 30))
    await deadlines.run()
    assert late.id not in [r.payload["task_id"] for r in await _rows(db, dl.KIND_REMINDER_SOON)]


async def test_overdue_alert_then_daily_summary(db: Database, clock: FakeClock, people) -> None:
    deadlines = dl.DeadlineService(db, clock)
    task = await _task(db, clock, people["owner"], people["sina"], at(12))
    clock._now = at(12, 1)
    await deadlines.run()
    await deadlines.run()
    assert [r.chat_id for r in await _rows(db, dl.KIND_OVERDUE)] == [SINA]
    watch = await _rows(db, dl.KIND_OVERDUE_WATCH)
    assert {r.chat_id for r in watch} == {people["owner"].telegram_id, FARID}
    assert watch[0].payload["assignee"] == "Sina"

    clock._now = at(10, 5, SAT + timedelta(days=1))
    await deadlines.run()
    daily = await _rows(db, dl.KIND_OVERDUE_DAILY)
    assert {(r.chat_id, r.payload["scope"]) for r in daily} == {
        (people["owner"].telegram_id, "all"), (FARID, "all"), (SINA, "mine")}
    rows = await deadlines.overdue_for(people["sina"], dl.SCOPE_MINE)
    assert [r.task.id for r in rows] == [task.id]


async def test_blocked_or_delivered_tasks_are_never_overdue(db: Database, clock: FakeClock, people) -> None:
    deadlines = dl.DeadlineService(db, clock)
    blocked = await _task(db, clock, people["owner"], people["sina"], at(12))
    delivered = await _task(db, clock, people["owner"], people["sina"], at(12))
    await _update_task(db, blocked.id, status=TaskStatus.BLOCKED)
    await _update_task(db, delivered.id, status=TaskStatus.IN_REVIEW, first_submitted_at=at(11))
    clock._now = at(13)
    assert await deadlines.run() == 0


async def test_changed_deadline_rearms_the_alert(db: Database, clock: FakeClock, people) -> None:
    deadlines = dl.DeadlineService(db, clock)
    tasks = TaskService(db, clock)
    task = await _task(db, clock, people["owner"], people["sina"], at(12))
    clock._now = at(12, 1)
    await deadlines.run()
    await tasks.change_due(people["owner"], task.id, at(15))
    clock._now = at(15, 1)
    await deadlines.run()
    assert len(await _rows(db, dl.KIND_OVERDUE)) == 2


async def test_reminder_renders_card_and_stale_one_is_dropped(db: Database, clock: FakeClock, people) -> None:
    users, tasks = UserService(db, clock, OWNER_TG), TaskService(db, clock)
    sender = FakeSender()
    outbox = OutboxSender(sender, OutboxStore(db, clock), users, tasks, clock,
                          deadlines=dl.DeadlineService(db, clock))
    task = await _task(db, clock, people["owner"], people["sina"], at(18))
    other = await _task(db, clock, people["owner"], people["sina"], at(18), title="دومی")
    clock._now = at(10, 1)
    await dl.DeadlineService(db, clock).run()
    await _update_task(db, other.id, status=TaskStatus.IN_REVIEW, first_submitted_at=at(10))
    sender.sent.clear()
    await outbox.deliver_due()
    reminders = [t for _, t in sender.sent if t.startswith("⏰")]
    assert len(reminders) == 1 and task.code in reminders[0]
    stale = [r for r in await _rows(db, dl.KIND_REMINDER_DAY) if r.payload["task_id"] == other.id][0]
    assert stale.status == NotificationStatus.FAILED


# ---- quiet hours -------------------------------------------------------------------


async def test_quiet_hours_hold_everything_until_9(db: Database, clock: FakeClock, people) -> None:
    clock._now = at(23, 30)
    async with db.transaction() as s:
        await enqueue(s, chat_id=SINA, kind="access.rejected", payload={}, dedupe_key="q1",
                      now=clock.now(), urgent=True)
    outbox = OutboxSender(FakeSender(), OutboxStore(db, clock), UserService(db, clock, OWNER_TG))
    assert await outbox.flush_urgent() == 0
    clock._now = at(8, 59, SAT + timedelta(days=1))
    assert await outbox.deliver_due() == 0
    clock._now = at(9, 0, SAT + timedelta(days=1))
    assert await outbox.deliver_due() == 1


async def test_owner_review_may_pass_quiet_hours_when_enabled(db: Database, clock: FakeClock, people) -> None:
    clock._now = at(1, 0)
    async with db.transaction() as s:
        s.add(Setting(key="owner_review_urgent_in_quiet_hours", value=True))
        await enqueue(s, chat_id=OWNER_TG, kind="review.requested", payload={}, dedupe_key="r1",
                      now=clock.now(), urgent=True)
        await enqueue(s, chat_id=OWNER_TG, kind="access.rejected", payload={}, dedupe_key="r2",
                      now=clock.now(), urgent=True)
    due = await OutboxStore(db, clock).due_urgent()
    assert [r.dedupe_key for r in due] == ["r1"]


# ---- recurrences (F10) ---------------------------------------------------------------


def _daily(assignee: User, **kw: Any) -> NewRecurrence:
    return NewRecurrence(title="استوری روزانه", assignee_id=assignee.id, rule=RecurrenceRule.DAILY,
                         create_time=time(8, 30), due_time=time(18, 0), estimated_minutes=30, **kw)


async def test_daily_recurrence_creates_one_task_per_day(db: Database, clock: FakeClock, people) -> None:
    service = RecurrenceService(db, clock)
    clock._now = at(8, 0)
    recurrence = await service.create(people["farid"], _daily(people["sina"]))
    assert await service.generate_due() == []
    clock._now = at(8, 31)
    created = await service.generate_due()
    assert len(created) == 1
    task = created[0]
    assert task.due_at == at(18) and task.recurrence_id == recurrence.id and task.recurrence_date == SAT
    assert task.assignee_id == people["sina"].id and task.estimated_minutes == 30
    assert await service.generate_due() == []
    assigned = [r for r in await _rows(db, "task.assigned") if r.payload["task_id"] == task.id]
    assert [r.chat_id for r in assigned] == [SINA]

    clock._now = at(9, 0, SAT + timedelta(days=1))
    assert len(await service.generate_due()) == 1
    await service.deactivate(people["farid"], recurrence.id)
    clock._now = at(9, 0, SAT + timedelta(days=2))
    assert await service.generate_due() == []


async def test_legacy_recurrence_cannot_create_unreviewed_tasks(db, clock, people):
    service = RecurrenceService(db, clock)
    clock._now = at(8, 0)
    recurrence = await service.create(people["farid"], _daily(
        people["sina"], approval_chain=ApprovalChain.NONE))
    assert recurrence.approval_chain == ApprovalChain.FINAL
    async with db.transaction() as session:
        legacy = await session.get(Recurrence, recurrence.id)
        legacy.approval_chain = ApprovalChain.NONE
    clock._now = at(8, 31)
    created = await service.generate_due()
    assert len(created) == 1 and created[0].approval_chain == ApprovalChain.FINAL


async def test_weekday_recurrence_uses_saturday_zero(db: Database, clock: FakeClock, people) -> None:
    service = RecurrenceService(db, clock)
    await service.create(people["farid"], NewRecurrence(
        title="جلسهٔ هفتگی", assignee_id=people["sina"].id, rule=RecurrenceRule.WEEKDAYS, weekdays=[1, 3],
        create_time=time(8, 0), due_time=time(12, 0)))
    clock._now = at(10)  # Saturday = 0
    assert await service.generate_due() == []
    clock._now = at(10, day=SAT + timedelta(days=1))  # Sunday = 1
    assert len(await service.generate_due()) == 1


async def test_recurrence_rules(db: Database, clock: FakeClock, people) -> None:
    service = RecurrenceService(db, clock)
    with pytest.raises(PermissionDenied):
        await service.create(people["sina"], _daily(people["sina"]))
    with pytest.raises(ValidationFailed):
        await service.create(people["farid"], NewRecurrence(
            title="x", assignee_id=people["sina"].id, rule=RecurrenceRule.DAILY,
            create_time=time(18), due_time=time(9)))
    with pytest.raises(ValidationFailed):
        await service.create(people["farid"], NewRecurrence(
            title="x", assignee_id=people["sina"].id, rule=RecurrenceRule.WEEKDAYS, weekdays=[]))
    await service.create(people["farid"], _daily(people["sina"]))
    async with db.transaction() as s:
        sina = await s.get(User, people["sina"].id)
        assert sina is not None
        sina.is_active = False
    clock._now = at(9)
    assert await service.generate_due() == []  # inactive assignee: skipped


# ---- reports -----------------------------------------------------------------------


async def test_saturday_report_numbers(db: Database, clock: FakeClock, people) -> None:
    owner, sina = people["owner"], people["sina"]
    async with db.transaction() as s:
        row = await s.get(User, sina.id)
        assert row is not None
        row.weekly_capacity_hours = 1
    late = await _task(db, clock, owner, sina, at(9), minutes=60)
    risky = await _task(db, clock, owner, sina, at(20), minutes=60)
    on_time = await _task(db, clock, owner, sina, at(18, day=SAT + timedelta(days=3)), minutes=30)
    await _update_task(db, on_time.id, status=TaskStatus.IN_REVIEW, review_stage=ReviewStage.FINAL,
                       first_submitted_at=at(9, 15))
    report = await ReportService(db, clock).saturday(people["farid"])
    assert [l.task.id for l in report.overdue] == [late.id]
    assert [l.task.id for l in report.at_risk] == [risky.id]
    assert [l.task.id for l in report.approvals] == [on_time.id]
    load = next(p for p in report.people if p.user.id == sina.id)
    assert load.open_count == 3 and load.week_count == 3 and load.week_minutes == 150
    assert load.over_capacity and load.on_time_percent == 100 and load.without_estimate == 0
    with pytest.raises(PermissionDenied):
        await ReportService(db, clock).saturday(sina)


async def test_group_messages_and_saturday_report_jobs(db: Database, clock: FakeClock, people, tmp_path) -> None:
    reports = ReportService(db, clock)
    backups = BackupService(None, tmp_path)
    assert await pj.PeriodicService(db, clock, reports, backups, None).group_messages() == []
    periodic = pj.PeriodicService(db, clock, reports, backups, GROUP)

    clock._now = at(9, 31)  # Saturday, nothing due today → no daily plan
    assert await periodic.group_messages() == []
    await _task(db, clock, people["owner"], people["sina"], at(17, day=SAT + timedelta(days=1)))
    clock._now = at(9, 31, SAT + timedelta(days=1))
    assert await periodic.group_messages() == [pj.KIND_DAILY_PLAN]
    assert await periodic.group_messages() == []
    plan = await reports.daily_plan()
    assert not plan.empty and plan.deliveries[0][0].id == people["sina"].id

    clock._now = at(18, 1, SAT + timedelta(days=5))  # Thursday
    assert pj.KIND_WEEKLY_SUMMARY in await periodic.group_messages()

    clock._now = at(9, 1, SAT + timedelta(days=7))  # next Saturday
    assert await periodic.saturday_report() == 2  # OWNER + Farid (stored RECEIVE_WEEKLY_REPORT)
    assert await periodic.saturday_report() == 0
    chats = sorted(r.chat_id for r in await _rows(db, pj.KIND_SATURDAY_REPORT))
    assert chats == [OWNER_TG, FARID]


async def test_report_and_group_rows_render(db: Database, clock: FakeClock, people) -> None:
    users, tasks = UserService(db, clock, OWNER_TG), TaskService(db, clock)
    sender = FakeSender()
    reports = ReportService(db, clock)
    outbox = OutboxSender(sender, OutboxStore(db, clock), users, tasks, clock, reports=reports,
                          deadlines=dl.DeadlineService(db, clock))
    await _task(db, clock, people["owner"], people["sina"], at(18), title="پوستر")
    async with db.transaction() as s:
        await enqueue(s, chat_id=FARID, kind=pj.KIND_SATURDAY_REPORT, payload={"user_id": people["farid"].id},
                      dedupe_key="rep", now=clock.now())
        await enqueue(s, chat_id=GROUP, kind=pj.KIND_DAILY_PLAN, payload={}, dedupe_key="plan", now=clock.now())
        await enqueue(s, chat_id=GROUP, kind=pj.KIND_WEEKLY_SUMMARY, payload={}, dedupe_key="sum", now=clock.now())
    sender.sent.clear()
    await outbox.deliver_due()
    by_chat = {chat: text for chat, text in sender.sent}
    assert by_chat[FARID].startswith("📊") and "Sina" in by_chat[FARID]
    group_texts = [t for c, t in sender.sent if c == GROUP]
    assert any(t.startswith("📅") and "پوستر" in t for t in group_texts)
    assert any(t.startswith("📊") for t in group_texts)
    assert all("عقب" not in t for t in group_texts)  # no delays in the group (§5.5)


# ---- heartbeat, backups, tick ---------------------------------------------------------


async def test_heartbeat_alerts_after_a_gap(db: Database, clock: FakeClock, people, tmp_path) -> None:
    periodic = pj.PeriodicService(db, clock, ReportService(db, clock), BackupService(None, tmp_path), None)
    assert await periodic.heartbeat() is None
    clock.advance(minutes=2)
    assert await periodic.heartbeat() is None
    clock.advance(minutes=20)
    assert await periodic.heartbeat() == timedelta(minutes=20)
    assert [r.chat_id for r in await _rows(db, pj.KIND_HEARTBEAT)] == [OWNER_TG]  # stored SYSTEM_ADMIN


def _make_db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE t (x INTEGER)")
    con.execute("INSERT INTO t VALUES (42)")
    con.commit()
    con.close()


async def test_daily_backup_copies_and_keeps_14(tmp_path: Path) -> None:
    source = tmp_path / "eventum.db"
    _make_db(source)
    folder = tmp_path / "backups"
    folder.mkdir()
    for i in range(KEEP + 3):
        (folder / backup_name(date(2026, 1, 1) + timedelta(days=i))).write_bytes(b"old")
    service = BackupService(source, folder)
    copy = await service.daily(date(2026, 11, 7))
    assert copy is not None and copy.name == "eventum-20261107.db"
    con = sqlite3.connect(copy)
    assert con.execute("SELECT x FROM t").fetchone() == (42,)
    con.close()
    assert len(list(folder.glob("eventum-*.db"))) == KEEP


async def test_weekly_backup_is_sent_to_system_admins(db: Database, clock: FakeClock, people,
                                                      tmp_path: Path) -> None:
    source = tmp_path / "eventum.db"
    _make_db(source)
    backups = BackupService(source, tmp_path / "backups")
    periodic = pj.PeriodicService(db, clock, ReportService(db, clock), backups, None)
    friday = SAT + timedelta(days=6)
    clock._now = at(4, 0, friday)
    assert await periodic.backups() == ["daily"]
    clock._now = at(4, 31, friday)
    assert await periodic.backups() == ["weekly"]
    assert await periodic.backups() == []
    rows = await _rows(db, pj.KIND_BACKUP_WEEKLY)
    assert [r.chat_id for r in rows] == [OWNER_TG] and rows[0].payload["path"].endswith(".db.gz")

    sender = FakeSender()
    clock._now = at(9, 0, friday)  # 04:31 is in quiet hours: the file goes out at 09:00
    outbox = OutboxSender(sender, OutboxStore(db, clock), UserService(db, clock, OWNER_TG), clock=clock)
    await outbox.deliver_due()
    assert [(chat, caption.startswith("🗄")) for chat, _, caption in sender.documents] == [(OWNER_TG, True)]


async def test_tick_keeps_going_when_a_job_fails(db: Database, clock: FakeClock, people, tmp_path) -> None:
    class Boom:
        async def generate_due(self) -> None:
            raise RuntimeError("boom")

    outbox = OutboxSender(FakeSender(), OutboxStore(db, clock), UserService(db, clock, OWNER_TG))
    scheduler = Scheduler(
        periodic=pj.PeriodicService(db, clock, ReportService(db, clock), BackupService(None, tmp_path), None),
        recurrences=Boom(),  # type: ignore[arg-type]
        deadlines=dl.DeadlineService(db, clock),
        outbox=outbox,
    )
    results = await scheduler.tick()
    assert results["recurrences"] is None and results["outbox"] == 0 and "deadlines" in results
