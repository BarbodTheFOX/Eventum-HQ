"""End-to-end through the real aiogram Dispatcher with a fake Telegram session.

No network: every Bot API call is recorded instead of sent.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import (
    AnswerCallbackQuery,
    CopyMessage,
    EditMessageText,
    SendMessage,
    TelegramMethod,
)
from aiogram.types import MessageId
from sqlalchemy import select

from eventum_hq.bot import texts
from eventum_hq.bot.app import build_dispatcher
from eventum_hq.bot.outbox import OutboxSender
from eventum_hq.core.config import load_settings
from eventum_hq.core.db import Database
from eventum_hq.models import Role, Task, TaskStatus, User
from eventum_hq.services.notifications import OutboxStore
from eventum_hq.services.permissions import ROLE_DEFAULT_CAPABILITIES, MenuItem
from eventum_hq.integrations.telegram_archive import TelegramArchive
from eventum_hq.services.deadlines import DeadlineService
from eventum_hq.services.delegations import DelegationService
from eventum_hq.services.outputs import LibraryService
from eventum_hq.services.recurrences import RecurrenceService
from eventum_hq.services.reports import ReportService
from eventum_hq.services.reels import ReelService
from eventum_hq.services.reviews import ReviewService
from eventum_hq.services.tasks import TaskService
from eventum_hq.services.users import UserService
from tests.conftest import OWNER_TG, FakeClock, add_user

FARID, SINA, AMIN = 2001, 2005, 2003


class RecordingSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []

    async def make_request(self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None) -> Any:
        self.calls.append(method)
        if isinstance(method, CopyMessage):
            return MessageId(message_id=5000 + len(self.calls))
        return True

    async def stream_content(self, *args: Any, **kwargs: Any):  # type: ignore[no-untyped-def]
        raise NotImplementedError
        yield b""  # pragma: no cover

    async def close(self) -> None:
        return None


ARCHIVE = -1009999


class Harness:
    def __init__(self, db: Database, clock: FakeClock, archive_channel_id: int | None = ARCHIVE) -> None:
        self.db = db
        self.clock = clock
        self.session = RecordingSession()
        self.bot = Bot(token="42:TEST", session=self.session)
        users = UserService(db, clock, OWNER_TG)
        self.tasks = TaskService(db, clock)
        self.reviews = ReviewService(db, clock)
        self.delegations = DelegationService(db, clock)
        self.reels = ReelService(db, clock)
        self.archive = TelegramArchive(self.bot, archive_channel_id)
        self.deadlines = DeadlineService(db, clock)
        self.reports = ReportService(db, clock)
        self.recurrences = RecurrenceService(db, clock)
        self.library = LibraryService(db)
        self.outbox = outbox = OutboxSender(self.bot, OutboxStore(db, clock), users, self.tasks, clock,
                                            self.reviews, self.archive, self.reels, self.deadlines, self.reports)
        settings = load_settings(_env_file=None, bot_token="42:TEST", owner_telegram_id=OWNER_TG,
                                 archive_channel_id=archive_channel_id)
        self.dp = build_dispatcher(
            settings=settings, users=users, tasks=self.tasks, reviews=self.reviews,
            delegations=self.delegations, reels=self.reels, archive=self.archive, outbox=outbox, clock=clock,
            recurrences=self.recurrences, reports=self.reports, library=self.library,
        )
        self._n = 0

    def _ts(self) -> int:
        return int(self.clock.now().timestamp())

    async def text(self, tg: int, text: str) -> None:
        self._n += 1
        await self.dp.feed_raw_update(self.bot, {
            "update_id": self._n,
            "message": {
                "message_id": self._n, "date": self._ts(),
                "chat": {"id": tg, "type": "private"},
                "from": {"id": tg, "is_bot": False, "first_name": f"U{tg}"},
                "text": text,
            },
        })

    async def press(self, tg: int, data: str) -> None:
        self._n += 1
        await self.dp.feed_raw_update(self.bot, {
            "update_id": self._n,
            "callback_query": {
                "id": str(self._n), "chat_instance": "ci", "data": data,
                "from": {"id": tg, "is_bot": False, "first_name": f"U{tg}"},
                "message": {
                    "message_id": 9000 + self._n, "date": self._ts(),
                    "chat": {"id": tg, "type": "private"}, "text": "old",
                },
            },
        })

    def texts_to(self, tg: int) -> list[str]:
        out = []
        for call in self.session.calls:
            if isinstance(call, (SendMessage, EditMessageText)) and call.chat_id == tg:
                out.append(call.text)
        return out

    def last_text(self, tg: int) -> str:
        return self.texts_to(tg)[-1]

    def alerts(self) -> list[str]:
        return [c.text for c in self.session.calls if isinstance(c, AnswerCallbackQuery) and c.text]

    def clear(self) -> None:
        self.session.calls.clear()


def _detach_routers() -> None:
    """aiogram routers are module singletons; free them so the next test can attach them."""
    from eventum_hq.bot.routers import (
        access, dates, deliver, errors, groups, library, menu, recurrences, reels, reports, review, start,
        task_create, tasks, team,
    )

    for module in (access, dates, deliver, errors, groups, library, menu, recurrences, reels, reports, review,
                   start, task_create, tasks, team):
        module.router._parent_router = None


@pytest.fixture
async def h(db: Database, clock: FakeClock, owner):  # type: ignore[no-untyped-def]
    for tg, role, name in [(FARID, Role.DIRECTOR, "Farid"), (SINA, Role.EDITOR, "Sina"),
                           (AMIN, Role.CONTENT_SPECIALIST, "Amin")]:
        await add_user(db, telegram_id=tg, role=role, full_name=name,
                       capabilities=list(ROLE_DEFAULT_CAPABILITIES[role]))
    _detach_routers()
    harness = Harness(db, clock)
    yield harness
    _detach_routers()


async def _user_id(db: Database, tg: int) -> int:
    async with db.read() as s:
        return (await s.execute(select(User.id).where(User.telegram_id == tg))).scalar_one()


async def _tasks(db: Database) -> list[Task]:
    async with db.read() as s:
        return list((await s.execute(select(Task).order_by(Task.id))).scalars())


async def _create_task_via_bot(h: Harness, title: str = "تامنیل اپیزود ۱۲") -> Task:
    sina_id = await _user_id(h.db, SINA)
    await h.text(FARID, texts.MENU_LABELS[MenuItem.NEW_TASK])
    assert h.last_text(FARID).startswith("➕")
    await h.text(FARID, title)
    assert h.last_text(FARID) == texts.NEW_TASK_DESCRIPTION
    await h.press(FARID, "nt:skip:")
    assert h.last_text(FARID) == texts.NEW_TASK_ASSIGNEE
    await h.press(FARID, f"nt:assignee:{sina_id}")
    assert h.last_text(FARID) == texts.DUE_DATE_PROMPT
    await h.text(FARID, "۱۴۰۵/۸/۲۰ ۱۸:۳۰")  # date + time in one go (Persian digits)
    assert h.last_text(FARID) == texts.NEW_TASK_ESTIMATE
    await h.text(FARID, "چند")  # invalid estimate
    assert h.last_text(FARID) == texts.INVALID_ESTIMATE
    await h.text(FARID, "۱٫۵ ساعت")
    assert h.last_text(FARID) == texts.NEW_TASK_SERIES
    await h.press(FARID, "nt:series:0")
    assert h.last_text(FARID) == texts.NEW_TASK_CHAIN
    await h.press(FARID, "nt:chain:FINAL")
    assert h.last_text(FARID).startswith("🧾")
    await h.press(FARID, "nt:create:")
    return (await _tasks(h.db))[-1]


async def test_farid_creates_task_and_sina_gets_card(h: Harness) -> None:
    task = await _create_task_via_bot(h)
    assert task.code == "T-0001" and task.title == "تامنیل اپیزود ۱۲"
    assert task.due_at == datetime(2026, 11, 11, 15, 0, tzinfo=UTC)  # 18:30 Tehran
    assert task.estimated_minutes == 90
    assert any("T-0001" in t for t in h.texts_to(FARID))
    to_sina = h.texts_to(SINA)
    assert len(to_sina) == 1 and to_sina[0].startswith(texts.NOTIFY_TASK_ASSIGNED.strip()[:5])
    assert "تامنیل اپیزود ۱۲" in to_sina[0] and "۱۴۰۵/۰۸/۲۰ ساعت ۱۸:۳۰" in to_sina[0]
    assert "۱ ساعت و ۳۰ دقیقه" in to_sina[0]


async def test_sina_lists_opens_and_starts(h: Harness) -> None:
    task = await _create_task_via_bot(h)
    h.clear()
    await h.text(SINA, texts.MENU_LABELS[MenuItem.MY_TASKS])
    assert "T-0001" in h.last_text(SINA)
    await h.text(SINA, "t-۱")  # code lookup with Persian digit
    assert "T-0001" in h.last_text(SINA) and texts.STATUS_LABELS[TaskStatus.TODO] in h.last_text(SINA)
    await h.press(SINA, f"t:s:{task.id}:0")
    assert texts.TASK_STARTED in h.alerts()
    assert (await _tasks(h.db))[0].status == TaskStatus.IN_PROGRESS


async def test_amin_cannot_see_or_start_sinas_task(h: Harness) -> None:
    task = await _create_task_via_bot(h)
    h.clear()
    await h.text(AMIN, "T-0001")
    assert h.last_text(AMIN) == texts.PERMISSION_DENIED
    await h.press(AMIN, f"t:s:{task.id}:0")  # forged callback
    assert texts.PERMISSION_DENIED in h.alerts()
    await h.press(AMIN, f"t:cy:{task.id}:0")
    assert (await _tasks(h.db))[0].status == TaskStatus.TODO


async def test_farid_changes_deadline_with_quick_buttons(h: Harness) -> None:
    task = await _create_task_via_bot(h)
    h.clear()
    await h.press(FARID, f"t:d:{task.id}:0")
    assert "T-0001" in h.last_text(FARID)
    await h.press(FARID, "dt:q:tomorrow")
    assert h.last_text(FARID).startswith("⏰")
    await h.press(FARID, "dt:t:1400")
    assert (await _tasks(h.db))[0].due_at == datetime(2026, 11, 8, 10, 30, tzinfo=UTC)
    assert any(t.startswith(texts.NOTIFY_TASK_DUE_CHANGED[:5]) for t in h.texts_to(SINA))


async def test_past_deadline_needs_confirmation(h: Harness) -> None:
    task = await _create_task_via_bot(h)
    h.clear()
    await h.press(FARID, f"t:d:{task.id}:0")
    await h.text(FARID, "1405/08/10 10:00")
    assert h.last_text(FARID).startswith("⚠️")
    await h.press(FARID, "dt:py:")
    assert (await _tasks(h.db))[0].due_at == datetime(2026, 11, 1, 6, 30, tzinfo=UTC)


async def test_invalid_date_is_rejected_and_flow_continues(h: Harness) -> None:
    sina_id = await _user_id(h.db, SINA)
    await h.text(FARID, texts.MENU_LABELS[MenuItem.NEW_TASK])
    await h.text(FARID, "x")
    await h.press(FARID, "nt:skip:")
    await h.press(FARID, f"nt:assignee:{sina_id}")
    await h.text(FARID, "1405/07/31")
    assert h.last_text(FARID) == texts.INVALID_DATE
    await h.text(FARID, "8/20")
    assert h.last_text(FARID).startswith("⏰")


async def test_cancel_and_menu_buttons_interrupt_flow(h: Harness) -> None:
    await h.text(FARID, texts.MENU_LABELS[MenuItem.NEW_TASK])
    await h.text(FARID, "/cancel")
    assert h.last_text(FARID) == texts.CANCELLED
    await h.text(FARID, "something")
    assert h.last_text(FARID) == texts.UNKNOWN_INPUT  # not captured as a title

    await h.text(FARID, texts.MENU_LABELS[MenuItem.NEW_TASK])
    await h.text(FARID, texts.MENU_LABELS[MenuItem.MY_TASKS])  # leaves the flow
    await h.text(FARID, "another")
    assert h.last_text(FARID) == texts.UNKNOWN_INPUT
    assert await _tasks(h.db) == []


async def test_flow_expires_after_30_minutes(h: Harness, clock: FakeClock) -> None:
    await h.text(FARID, texts.MENU_LABELS[MenuItem.NEW_TASK])
    clock.advance(minutes=31)
    await h.text(FARID, "late title")
    assert texts.FLOW_EXPIRED in h.texts_to(FARID)
    assert h.last_text(FARID) == texts.UNKNOWN_INPUT


async def test_flow_survives_29_minutes(h: Harness, clock: FakeClock) -> None:
    await h.text(FARID, texts.MENU_LABELS[MenuItem.NEW_TASK])
    clock.advance(minutes=29)
    await h.text(FARID, "title")
    assert h.last_text(FARID) == texts.NEW_TASK_DESCRIPTION


async def test_editor_cannot_open_new_task_or_all_tasks(h: Harness) -> None:
    await h.text(SINA, texts.MENU_LABELS[MenuItem.NEW_TASK])
    assert h.last_text(SINA) == texts.PERMISSION_DENIED
    await h.text(SINA, texts.MENU_LABELS[MenuItem.ALL_TASKS])
    assert h.last_text(SINA) == texts.PERMISSION_DENIED
    await h.press(SINA, "tl:open:0:0")  # forged list button
    assert texts.PERMISSION_DENIED in h.alerts()


async def test_all_tasks_filters_and_reassign(h: Harness) -> None:
    task = await _create_task_via_bot(h)
    amin_id = await _user_id(h.db, AMIN)
    h.clear()
    await h.text(FARID, texts.MENU_LABELS[MenuItem.ALL_TASKS])
    assert h.last_text(FARID) == texts.ALL_TASKS_MENU
    await h.press(FARID, "tl:open:0:0")
    assert "T-0001" in h.last_text(FARID)
    await h.press(FARID, f"t:r:{task.id}:0")
    await h.press(FARID, f"t:a:{task.id}:{amin_id}")
    assert (await _tasks(h.db))[0].assignee_id == amin_id
    assert any("T-0001" in t for t in h.texts_to(AMIN))
    assert any(t.startswith("↪️") for t in h.texts_to(SINA))


async def test_history_and_cancel(h: Harness) -> None:
    task = await _create_task_via_bot(h)
    h.clear()
    await h.press(FARID, f"t:c:{task.id}:0")
    assert texts.CONFIRM_CANCEL_TASK.strip()[:3] in h.last_text(FARID)
    await h.press(FARID, f"t:cy:{task.id}:0")
    assert (await _tasks(h.db))[0].status == TaskStatus.CANCELLED
    await h.press(FARID, f"t:h:{task.id}:0")
    history = h.last_text(FARID)
    assert texts.AUDIT_LABELS["task.created"] in history and texts.AUDIT_LABELS["task.cancelled"] in history
    assert any(t.startswith("❌") for t in h.texts_to(SINA))


async def test_voice_brief_is_kept_and_resent(h: Harness) -> None:
    from aiogram.methods import SendVoice

    sina_id = await _user_id(h.db, SINA)
    await h.text(FARID, texts.MENU_LABELS[MenuItem.NEW_TASK])
    await h.text(FARID, "ویس بریف")
    h._n += 1
    await h.dp.feed_raw_update(h.bot, {
        "update_id": h._n,
        "message": {
            "message_id": h._n, "date": h._ts(),
            "chat": {"id": FARID, "type": "private"},
            "from": {"id": FARID, "is_bot": False, "first_name": "Farid"},
            "voice": {"file_id": "VOICE1", "file_unique_id": "U1", "duration": 4, "file_size": 1000},
            "caption": "توضیح صوتی",
        },
    })
    assert h.last_text(FARID) == texts.NEW_TASK_ASSIGNEE
    await h.press(FARID, f"nt:assignee:{sina_id}")
    await h.text(FARID, "8/20 10:00")
    await h.press(FARID, "nt:estimate:0")  # no estimate
    await h.press(FARID, "nt:series:0")
    await h.press(FARID, "nt:chain:FINAL")
    await h.press(FARID, "nt:create:")
    task = (await _tasks(h.db))[-1]
    assert task.description == "توضیح صوتی"
    assert task.estimated_minutes is None
    h.clear()
    await h.press(SINA, f"t:b:{task.id}:0")
    voices = [c for c in h.session.calls if isinstance(c, SendVoice)]
    assert len(voices) == 1 and voices[0].voice == "VOICE1" and voices[0].chat_id == SINA
