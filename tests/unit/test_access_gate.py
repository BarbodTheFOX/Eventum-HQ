"""Whitelist gate (handoff §3.3, §6.3)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from aiogram.types import CallbackQuery, Chat, Message, Update
from aiogram.types import User as TgUser

from eventum_hq.bot.middlewares import (
    AccessMiddleware,
    is_allowed,
    is_join_callback,
    is_start_command,
    should_leave_chat,
)
from eventum_hq.models import AccessStatus, Role
from eventum_hq.services.users import UserService
from tests.conftest import OWNER_TG, add_user


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("/start", True),
        ("/start abc", True),
        ("/start@EventumHQTestBot", True),
        ("  /START  ", True),
        ("/starter", False),
        ("start", False),
        ("/menu", False),
        (None, False),
        ("", False),
    ],
)
def test_is_start_command(text: str | None, expected: bool) -> None:
    assert is_start_command(text) is expected


@pytest.mark.parametrize(
    ("chat_type", "known", "entry", "allowed"),
    [
        ("private", True, False, True),
        ("private", True, True, True),
        ("private", False, True, True),  # unknown may only /start
        ("private", False, False, False),
        ("group", True, False, False),  # never answer in groups
        ("group", True, True, False),
        ("supergroup", True, True, False),
        ("channel", True, False, False),
        (None, True, False, False),
    ],
)
def test_is_allowed(chat_type: str | None, known: bool, entry: bool, allowed: bool) -> None:
    assert is_allowed(chat_type=chat_type, is_known_user=known, is_entry=entry) is allowed


@pytest.mark.parametrize(
    ("chat_type", "chat_id", "team", "leave"),
    [
        ("group", -100, -100, False),
        ("supergroup", -100, -100, False),
        ("supergroup", -200, -100, True),
        ("group", -200, None, True),
        ("channel", -300, -100, False),  # archive channel is fine
        ("private", 5, -100, False),
    ],
)
def test_should_leave_chat(chat_type: str, chat_id: int, team: int | None, leave: bool) -> None:
    assert should_leave_chat(chat_type=chat_type, chat_id=chat_id, team_group_id=team) is leave


# ---- middleware with real aiogram objects -------------------------------------

STRANGER_TG = 555


def _message_update(tg_id: int, text: str, chat_type: str = "private") -> tuple[Update, dict]:
    tg_user = TgUser(id=tg_id, is_bot=False, first_name="X")
    chat = Chat(id=tg_id if chat_type == "private" else -100, type=chat_type)
    msg = Message(
        message_id=1, date=datetime.now(UTC), chat=chat, from_user=tg_user, text=text
    )
    return Update(update_id=1, message=msg), {"event_chat": chat, "event_from_user": tg_user}


class Recorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, event: Any, data: dict[str, Any]) -> str:
        self.calls.append(dict(data))
        return "handled"


async def test_unknown_user_is_blocked_except_start(users: UserService, owner) -> None:
    mw, handler = AccessMiddleware(users), Recorder()

    update, data = _message_update(STRANGER_TG, "hello")
    assert await mw(handler, update, data) is None
    assert handler.calls == []

    update, data = _message_update(STRANGER_TG, "/start")
    assert await mw(handler, update, data) == "handled"
    assert handler.calls[-1]["current_user"] is None


async def test_known_user_passes_with_current_user(users: UserService, owner) -> None:
    mw, handler = AccessMiddleware(users), Recorder()
    update, data = _message_update(OWNER_TG, "anything")
    assert await mw(handler, update, data) == "handled"
    assert handler.calls[-1]["current_user"].telegram_id == OWNER_TG


async def test_known_user_in_group_is_ignored(users: UserService, owner) -> None:
    mw, handler = AccessMiddleware(users), Recorder()
    update, data = _message_update(OWNER_TG, "/start", chat_type="supergroup")
    assert await mw(handler, update, data) is None
    assert handler.calls == []


@pytest.mark.parametrize(
    ("is_active", "status"),
    [(False, AccessStatus.APPROVED), (True, AccessStatus.PENDING), (True, AccessStatus.REJECTED)],
)
async def test_inactive_or_unapproved_user_is_blocked(
    db, users: UserService, is_active: bool, status: AccessStatus
) -> None:
    await add_user(db, telegram_id=777, role=Role.EDITOR, is_active=is_active, access_status=status)
    mw, handler = AccessMiddleware(users), Recorder()
    update, data = _message_update(777, "/menu")
    assert await mw(handler, update, data) is None
    assert handler.calls == []


async def test_unknown_user_callback_is_dropped(users: UserService, owner, monkeypatch) -> None:
    tg_user = TgUser(id=STRANGER_TG, is_bot=False, first_name="X")
    chat = Chat(id=STRANGER_TG, type="private")
    msg = Message(message_id=1, date=datetime.now(UTC), chat=chat, from_user=tg_user, text="x")
    cq = CallbackQuery(id="1", from_user=tg_user, chat_instance="c", message=msg, data="acc:ok:1")
    answered: list[bool] = []

    async def fake_answer(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        answered.append(True)

    monkeypatch.setattr(CallbackQuery, "answer", fake_answer)
    update = Update(update_id=2, callback_query=cq)
    handler = Recorder()
    result = await AccessMiddleware(users)(
        handler, update, {"event_chat": chat, "event_from_user": tg_user}
    )
    assert result is None
    assert handler.calls == []
    assert answered == [True]


@pytest.mark.parametrize(
    ("data", "expected"),
    [("join:EDITOR", True), ("join:", True), ("acc:ok:1", False), ("joiner", False), (None, False)],
)
def test_is_join_callback(data: str | None, expected: bool) -> None:
    assert is_join_callback(data) is expected


async def test_unknown_user_role_picker_callback_passes(users: UserService, owner) -> None:
    tg_user = TgUser(id=STRANGER_TG, is_bot=False, first_name="X")
    chat = Chat(id=STRANGER_TG, type="private")
    msg = Message(message_id=1, date=datetime.now(UTC), chat=chat, from_user=tg_user, text="x")
    cq = CallbackQuery(id="1", from_user=tg_user, chat_instance="c", message=msg, data="join:EDITOR")
    handler = Recorder()
    result = await AccessMiddleware(users)(
        handler, Update(update_id=3, callback_query=cq), {"event_chat": chat, "event_from_user": tg_user}
    )
    assert result == "handled"
    assert handler.calls[-1]["current_user"] is None
