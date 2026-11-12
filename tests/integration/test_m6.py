"""M6: offboarding (F15), /health, /backup and error alerts (handoff §6.4, §6.5)."""

from __future__ import annotations

import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from eventum_hq.bot import texts
from eventum_hq.bot.keyboards.members import MemberAction, MemberCb
from eventum_hq.core.db import Database
from eventum_hq.core.errors import InvalidTransition, PermissionDenied, ValidationFailed
from eventum_hq.models import (
    AuditEvent,
    Capability,
    Delegation,
    Notification,
    NotificationStatus,
    Recurrence,
    RecurrenceRule,
    Role,
    Task,
    TaskStatus,
    User,
)
from eventum_hq.scheduler.tick import Scheduler
from eventum_hq.services.backup import BackupService
from eventum_hq.services.delegations import DelegationService
from eventum_hq.services.offboarding import KIND_USER_DEACTIVATED, OffboardingService
from eventum_hq.services.permissions import ROLE_DEFAULT_CAPABILITIES, MenuItem
from eventum_hq.services.periodic import PeriodicService
from eventum_hq.services.recurrences import NewRecurrence, RecurrenceService
from eventum_hq.services.reports import ReportService
from eventum_hq.services.system import KIND_SYSTEM_ERROR, SystemService
from eventum_hq.services.tasks import KIND_TASK_ASSIGNED, NewTask, TaskService
from tests.conftest import OWNER_TG, FakeClock, add_user
from tests.integration.test_bot_flows import AMIN, FARID, SINA, Harness, _detach_routers

MOHADESEH = 2004


@pytest.fixture
async def team(db: Database, owner: User) -> dict[str, User]:
    people = {"barbod": owner}
    for key, tg, role, name in [("farid", FARID, Role.DIRECTOR, "فرید"), ("amin", AMIN, Role.CONTENT_SPECIALIST, "امین"),
                                ("sina", SINA, Role.EDITOR, "سینا"), ("mohadeseh", MOHADESEH, Role.DESIGNER, "محدثه")]:
        people[key] = await add_user(db, telegram_id=tg, role=role, full_name=name,
                                     capabilities=list(ROLE_DEFAULT_CAPABILITIES[role]))
    return people


@pytest.fixture
def offboarding(db: Database, clock: FakeClock) -> OffboardingService:
    return OffboardingService(db, clock)


async def _task(db: Database, clock: FakeClock, team, assignee: str, title: str = "کار") -> Task:  # type: ignore[no-untyped-def]
    return await TaskService(db, clock).create_generic(
        team["farid"], NewTask(title=title, assignee_id=team[assignee].id, due_at=clock.now() + timedelta(days=1)))


async def _all(db: Database, model):  # type: ignore[no-untyped-def]
    async with db.read() as s:
        return list((await s.execute(select(model).order_by(model.id))).scalars())


async def _reload(db: Database, model, row_id: int):  # type: ignore[no-untyped-def]
    async with db.read() as s:
        return await s.get(model, row_id)


# ---- offboarding service -----------------------------------------------------------------


async def test_deactivate_hands_over_and_warns(db: Database, clock: FakeClock, team, offboarding) -> None:  # type: ignore[no-untyped-def]
    t1 = await _task(db, clock, team, "amin", "تامنیل")
    t2 = await _task(db, clock, team, "amin", "کپشن")
    done = await _task(db, clock, team, "amin", "قدیمی")
    await TaskService(db, clock).cancel(team["farid"], done.id)
    recurrence = await RecurrenceService(db, clock).create(team["farid"], NewRecurrence(
        title="استوری روزانه", assignee_id=team["amin"].id, rule=RecurrenceRule.DAILY))
    await DelegationService(db, clock).create(team["farid"], team["amin"].id, clock.now() + timedelta(days=2))
    pending_before = [n for n in await _all(db, Notification)
                      if n.chat_id == AMIN and n.status == NotificationStatus.PENDING]
    assert pending_before

    view = await offboarding.deactivate(team["farid"], team["amin"].id)

    amin = await _reload(db, User, team["amin"].id)
    assert amin.is_active is False and amin.deactivated_at == clock.now() and amin.full_name == "امین"
    assert {t.id for t in view.open_tasks} == {t1.id, t2.id}  # the cancelled one is not open work
    assert [r.id for r in view.recurrences] == [recurrence.id]
    gaps = {g.capability: g.covered for g in view.capabilities}
    assert gaps == {Capability.CREATE_REEL: False, Capability.REVIEW_L1: False}
    assert view.delegation_revoked
    assert (await _all(db, Delegation))[0].revoked_at == clock.now()
    assert not [n for n in await _all(db, Notification)
                if n.chat_id == AMIN and n.status == NotificationStatus.PENDING]
    events = [e for e in await _all(db, AuditEvent) if e.action == "user.deactivated"]
    assert len(events) == 1 and events[0].actor_id == team["farid"].id
    assert set(events[0].data["open_tasks"]) == {t1.id, t2.id}
    # the OWNER is warned about the capabilities nobody else has
    warn = [n for n in await _all(db, Notification) if n.kind == KIND_USER_DEACTIVATED]
    assert [n.chat_id for n in warn] == [OWNER_TG]
    assert set(warn[0].payload["missing"]) == {"CREATE_REEL", "REVIEW_L1"}

    # hand-over list and orphan recurrence count
    assert [r.user.id for r in await offboarding.pending_handovers(team["farid"])] == [team["amin"].id]
    assert await offboarding.orphan_recurrences(team["farid"]) == 1

    moved = await offboarding.transfer_all(team["farid"], team["amin"].id, team["sina"].id)
    assert {t.id for t in moved} == {t1.id, t2.id}
    for task_id in (t1.id, t2.id):
        assert (await _reload(db, Task, task_id)).assignee_id == team["sina"].id
    assert len([n for n in await _all(db, Notification)
                if n.kind == KIND_TASK_ASSIGNED and n.chat_id == SINA]) >= 2
    reassigned = [e for e in await _all(db, AuditEvent) if e.action == "task.reassigned"]
    assert {e.data["reason"] for e in reassigned} == {"offboarding"}
    assert (await _reload(db, Task, done.id)).assignee_id == team["amin"].id  # history untouched

    await offboarding.reassign_recurrence(team["farid"], recurrence.id, team["mohadeseh"].id)
    assert (await _reload(db, Recurrence, recurrence.id)).assignee_id == team["mohadeseh"].id
    assert await offboarding.orphan_recurrences(team["farid"]) == 0
    assert await offboarding.pending_handovers(team["farid"]) == []


async def test_deactivate_rules(db: Database, clock: FakeClock, team, offboarding) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(PermissionDenied):
        await offboarding.deactivate(team["sina"], team["mohadeseh"].id)  # no MANAGE_USERS
    with pytest.raises(ValidationFailed, match="deactivate_self"):
        await offboarding.deactivate(team["farid"], team["farid"].id)
    with pytest.raises(ValidationFailed, match="deactivate_owner"):
        await offboarding.deactivate(team["farid"], team["barbod"].id)
    await offboarding.deactivate(team["barbod"], team["mohadeseh"].id)  # OWNER may too
    with pytest.raises(InvalidTransition):
        await offboarding.deactivate(team["farid"], team["mohadeseh"].id)
    # the OWNER who did it gets no extra notification
    assert not [n for n in await _all(db, Notification) if n.kind == KIND_USER_DEACTIVATED]


async def test_handover_only_from_inactive_people(db: Database, clock: FakeClock, team, offboarding) -> None:  # type: ignore[no-untyped-def]
    task = await _task(db, clock, team, "sina")
    with pytest.raises(ValidationFailed, match="handover_active_user"):
        await offboarding.transfer_task(team["farid"], task.id, team["mohadeseh"].id)
    with pytest.raises(ValidationFailed, match="handover_active_user"):
        await offboarding.transfer_all(team["farid"], team["sina"].id, team["mohadeseh"].id)
    await offboarding.deactivate(team["farid"], team["sina"].id)
    with pytest.raises(ValidationFailed, match="assignee_inactive"):
        await offboarding.transfer_task(team["farid"], task.id, team["sina"].id)
    with pytest.raises(PermissionDenied):
        await offboarding.transfer_task(team["mohadeseh"], task.id, team["farid"].id)
    moved = await offboarding.transfer_task(team["farid"], task.id, team["mohadeseh"].id)
    assert moved.assignee_id == team["mohadeseh"].id


async def test_recurrence_after_handover_creates_for_new_person(db: Database, clock: FakeClock, team,  # type: ignore[no-untyped-def]
                                                                offboarding) -> None:
    recurrences = RecurrenceService(db, clock)
    rec = await recurrences.create(team["farid"], NewRecurrence(title="بک‌آپ پیج", assignee_id=team["sina"].id,
                                                               rule=RecurrenceRule.DAILY))
    await offboarding.deactivate(team["farid"], team["sina"].id)
    clock.advance(hours=1)  # 09:00 Tehran > 08:30 create time
    assert await recurrences.generate_due() == []  # inactive assignee: nothing created
    await offboarding.reassign_recurrence(team["farid"], rec.id, team["mohadeseh"].id)
    created = await recurrences.generate_due()
    assert [t.assignee_id for t in created] == [team["mohadeseh"].id]


# ---- error alerts ---------------------------------------------------------------------------


async def test_error_alert_rate_limited(db: Database, clock: FakeClock, team) -> None:  # type: ignore[no-untyped-def]
    system = SystemService(db, clock, BackupService(None, Path("x")), secrets=["42:SECRET"])
    assert await system.report_error("RuntimeError", "button t", "boom 42:SECRET") == 1  # OWNER = SYSTEM_ADMIN
    clock.advance(minutes=3)
    assert await system.report_error("RuntimeError", "button t", "again") == 0  # same type, same 10 minutes
    assert await system.report_error("KeyError", "message", "other") == 1  # other type
    clock.advance(minutes=10)
    assert await system.report_error("RuntimeError", "button t", "later") == 1
    rows = [n for n in await _all(db, Notification) if n.kind == KIND_SYSTEM_ERROR]
    assert len(rows) == 3 and all(n.chat_id == OWNER_TG and n.urgent for n in rows)
    assert "SECRET" not in rows[0].payload["message"]


async def test_tick_failure_is_reported(db: Database, clock: FakeClock, team) -> None:  # type: ignore[no-untyped-def]
    calls: list[tuple[str, str, str]] = []

    async def on_error(kind: str, where: str, message: str) -> int:
        calls.append((kind, where, message))
        return 1

    class Broken:
        async def deliver_due(self) -> int:
            raise RuntimeError("telegram down")

    reports = ReportService(db, clock)
    scheduler = Scheduler(periodic=PeriodicService(db, clock, reports, BackupService(None, Path("x")), None),
                          recurrences=RecurrenceService(db, clock), deadlines=_NoDeadlines(),  # type: ignore[arg-type]
                          outbox=Broken(), on_error=on_error)
    results = await scheduler.tick()
    assert results["outbox"] is None and results["heartbeat"] is None
    assert calls == [("RuntimeError", "tick:outbox", "telegram down")]


class _NoDeadlines:
    async def run(self) -> None:
        return None


# ---- /health and /backup (service) ------------------------------------------------------------


async def test_health_report(db: Database, clock: FakeClock, team, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    db_file = tmp_path / "eventum.db"
    sqlite3.connect(db_file).close()
    backups = BackupService(db_file, tmp_path / "backups")
    system = SystemService(db, clock, backups, started_at=clock.now() - timedelta(hours=26))
    with pytest.raises(PermissionDenied):
        await system.health(team["sina"])
    report = await system.health(team["barbod"])
    assert report.last_tick is None and not report.tick_ok and report.last_backup is None
    assert report.uptime == timedelta(hours=26) and report.active_users == 5

    reports = ReportService(db, clock)
    await PeriodicService(db, clock, reports, backups, None).heartbeat()
    clock.advance(minutes=2)
    packed = await system.backup_now(team["barbod"])
    assert packed.sendable and packed.path.exists() and packed.path.name.endswith(".db.gz")
    report = await system.health(team["barbod"])
    assert report.tick_ok and report.last_backup is not None and report.db_size is not None
    assert [e.action for e in await _all(db, AuditEvent) if e.action.startswith("system.")] == [
        "system.backup_manual"]
    clock.advance(minutes=10)
    assert not (await system.health(team["barbod"])).tick_ok


async def test_backup_needs_admin_and_sqlite(db: Database, clock: FakeClock, team) -> None:  # type: ignore[no-untyped-def]
    system = SystemService(db, clock, BackupService(None, Path("x")))
    with pytest.raises(PermissionDenied):
        await system.backup_now(team["farid"])  # DIRECTOR is not SYSTEM_ADMIN
    with pytest.raises(ValidationFailed, match="backup_disabled"):
        await system.backup_now(team["barbod"])


# ---- bot ---------------------------------------------------------------------------------------


@pytest.fixture
async def h(db: Database, clock: FakeClock, team, tmp_path: Path):  # type: ignore[no-untyped-def]
    db_file = tmp_path / "eventum.db"
    sqlite3.connect(db_file).close()
    _detach_routers()
    harness = Harness(db, clock, backups=BackupService(db_file, tmp_path / "backups"))
    yield harness
    _detach_routers()


def _mb(action: MemberAction, arg: int = 0, to: int = 0, back: int = 0) -> str:
    return MemberCb(action=action, arg=arg, to=to, back=back).pack()


async def test_bot_offboarding_flow(h: Harness, db: Database, clock: FakeClock, team) -> None:  # type: ignore[no-untyped-def]
    amin, sina = team["amin"], team["sina"]
    task = await _task(db, clock, team, "amin", "تامنیل اپیزود")
    await h.text(FARID, texts.MENU_LABELS[MenuItem.TEAM])
    assert any(texts.BTN_MEMBERS in str(c) for c in h.session.calls if getattr(c, "chat_id", None) == FARID)

    await h.press(FARID, _mb(MemberAction.LIST))
    assert h.last_text(FARID).startswith("👤")
    await h.press(FARID, _mb(MemberAction.OPEN, amin.id))
    card = h.last_text(FARID)
    assert "امین" in card and "بررسی مرحلهٔ اول" in card and task.code in card

    await h.press(FARID, _mb(MemberAction.DEACT_ASK, amin.id))
    assert h.last_text(FARID).startswith("⛔️")
    await h.press(FARID, _mb(MemberAction.DEACT_YES, amin.id))
    summary = h.last_text(FARID)
    assert "غیرفعال شد" in summary and "بررسی مرحلهٔ اول" in summary and "ساخت ریل" in summary
    assert any("غیرفعال شد" in t for t in h.texts_to(OWNER_TG))  # OWNER warned right away

    # the deactivated person can no longer use the bot
    h.clear()
    await h.text(AMIN, texts.MENU_LABELS[MenuItem.MY_TASKS])
    assert not any(task.code in t for t in h.texts_to(AMIN))

    # team home shows the pending hand-over; hand everything to Sina
    await h.text(FARID, texts.MENU_LABELS[MenuItem.TEAM])
    assert "هنوز به کسی سپرده نشده" in h.last_text(FARID)
    await h.press(FARID, _mb(MemberAction.HANDOVERS))
    await h.press(FARID, _mb(MemberAction.ALL_PICK, amin.id))
    assert "به چه کسی سپرده شود" in h.last_text(FARID)
    await h.press(FARID, _mb(MemberAction.ALL_TO, amin.id, sina.id, amin.id))
    assert "سپرده شد" in h.last_text(FARID)
    assert (await _reload(db, Task, task.id)).assignee_id == sina.id
    assert any(task.code in t for t in h.texts_to(SINA))  # new assignee gets the card


async def test_bot_members_need_manage_users(h: Harness, team) -> None:  # type: ignore[no-untyped-def]
    await h.press(SINA, _mb(MemberAction.LIST))
    assert texts.PERMISSION_DENIED in h.alerts()
    await h.press(SINA, _mb(MemberAction.DEACT_YES, team["mohadeseh"].id))
    assert (await _reload(h.db, User, team["mohadeseh"].id)).is_active


async def test_bot_health_and_backup(h: Harness, team) -> None:  # type: ignore[no-untyped-def]
    await h.text(SINA, "/health")
    assert h.last_text(SINA) == texts.PERMISSION_DENIED
    await h.text(OWNER_TG, "/health")
    assert h.last_text(OWNER_TG).startswith("🩺")
    await h.text(FARID, "/backup")
    assert h.last_text(FARID) == texts.PERMISSION_DENIED
    h.clear()
    await h.text(OWNER_TG, "/backup")
    from aiogram.methods import SendDocument
    docs = [c for c in h.session.calls if isinstance(c, SendDocument)]
    assert len(docs) == 1 and docs[0].chat_id == OWNER_TG


async def test_bot_help_shows_admin_commands_to_admins_only(h: Harness, team) -> None:  # type: ignore[no-untyped-def]
    await h.text(OWNER_TG, "/help")
    assert "/health" in h.last_text(OWNER_TG)
    await h.text(SINA, "/help")
    assert "/health" not in h.last_text(SINA) and "📤 تحویل" in h.last_text(SINA)


async def test_bot_error_is_reported(h: Harness, team, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    async def broken(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("report exploded")

    monkeypatch.setattr(h.reports, "saturday", broken)
    await h.text(FARID, texts.MENU_LABELS[MenuItem.REPORT])
    assert h.last_text(FARID) == texts.ERROR_REPORTED
    alert = [t for t in h.texts_to(OWNER_TG) if t.startswith("🚨")]
    assert len(alert) == 1 and "RuntimeError" in alert[0] and "report exploded" in alert[0]
    await h.text(FARID, texts.MENU_LABELS[MenuItem.REPORT])  # same error again: no second alert
    assert len([t for t in h.texts_to(OWNER_TG) if t.startswith("🚨")]) == 1
