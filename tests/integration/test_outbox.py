"""Urgent outbox delivery (M0 part of handoff §6.2). No real Telegram calls."""

from __future__ import annotations

from typing import Any

from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from sqlalchemy import select

from eventum_hq.bot import texts
from eventum_hq.bot.keyboards.access import AccessAction, AccessCb
from eventum_hq.models import Role
from eventum_hq.services.permissions import MenuItem
from eventum_hq.bot.outbox import OutboxSender
from eventum_hq.core.db import Database
from eventum_hq.models import Notification, NotificationStatus
from eventum_hq.services.notifications import MAX_ATTEMPTS, OutboxStore, enqueue
from eventum_hq.services.users import UserService
from tests.conftest import OWNER_TG, FakeClock

STRANGER_TG = 555


class FakeSender:
    def __init__(self, fail_with: Exception | None = None) -> None:
        self.sent: list[tuple[int, str, Any]] = []
        self.fail_with = fail_with

    async def send_message(self, chat_id: int, text: str, **kwargs: Any) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.sent.append((chat_id, text, kwargs.get("reply_markup")))


async def _rows(db: Database) -> list[Notification]:
    async with db.read() as s:
        return list((await s.execute(select(Notification).order_by(Notification.id))).scalars())


async def test_full_access_flow_delivers_card_then_approval(
    db: Database, users: UserService, owner, clock: FakeClock
) -> None:
    sender = FakeSender()
    outbox = OutboxSender(sender, OutboxStore(db, clock), users)

    req = await users.request_access(
        telegram_id=STRANGER_TG, full_name="Sina <b>", username="sina", role="CONTENT_SPECIALIST"
    )
    assert await outbox.flush_urgent() == 1
    chat_id, text, markup = sender.sent[0]
    assert chat_id == OWNER_TG
    assert "Sina &lt;b&gt;" in text  # user input is HTML-escaped
    assert "@sina" in text and str(STRANGER_TG) in text
    assert texts.ROLE_LABELS[Role.CONTENT_SPECIALIST] in text
    assert isinstance(markup, InlineKeyboardMarkup)
    first_row, second_row = markup.inline_keyboard
    assert texts.ROLE_LABELS[Role.CONTENT_SPECIALIST] in first_row[0].text
    assert AccessCb.unpack(first_row[0].callback_data) == AccessCb(
        action=AccessAction.APPROVE, user_id=req.user.id
    )
    assert AccessCb.unpack(second_row[0].callback_data).action == AccessAction.PICK_ROLE
    assert AccessCb.unpack(second_row[1].callback_data).action == AccessAction.REJECT

    # nothing is sent twice
    assert await outbox.flush_urgent() == 0

    await users.approve_access(owner, req.user.id)
    assert await outbox.flush_urgent() == 1
    chat_id, text, markup = sender.sent[1]
    assert chat_id == STRANGER_TG
    assert texts.ROLE_LABELS[Role.CONTENT_SPECIALIST] in text
    assert isinstance(markup, ReplyKeyboardMarkup)  # the approved user's own menu
    labels = [b.text for row in markup.keyboard for b in row]
    assert texts.MENU_LABELS[MenuItem.NEW_REEL] in labels
    assert texts.MENU_LABELS[MenuItem.TEAM] not in labels
    assert all(r.status == NotificationStatus.SENT and r.sent_at for r in await _rows(db))


async def test_failures_are_counted_then_marked_failed(
    db: Database, users: UserService, clock: FakeClock
) -> None:
    async with db.transaction() as s:
        await enqueue(
            s, chat_id=1, kind="access.rejected", payload={"user_id": 1},
            dedupe_key="k1", now=clock.now(), urgent=True,
        )
    outbox = OutboxSender(FakeSender(fail_with=RuntimeError("network down")), OutboxStore(db, clock), users)
    for _ in range(MAX_ATTEMPTS - 1):
        assert await outbox.flush_urgent() == 0
    row = (await _rows(db))[0]
    assert row.status == NotificationStatus.PENDING and row.attempts == MAX_ATTEMPTS - 1
    assert "network down" in (row.last_error or "")

    await outbox.flush_urgent()
    row = (await _rows(db))[0]
    assert row.status == NotificationStatus.FAILED and row.attempts == MAX_ATTEMPTS


async def test_blocked_bot_is_a_permanent_failure(
    db: Database, users: UserService, clock: FakeClock
) -> None:
    async with db.transaction() as s:
        await enqueue(
            s, chat_id=1, kind="access.rejected", payload={"user_id": 1},
            dedupe_key="k2", now=clock.now(), urgent=True,
        )
    err = TelegramForbiddenError(method=SendMessage(chat_id=1, text="x"), message="bot was blocked")
    outbox = OutboxSender(FakeSender(fail_with=err), OutboxStore(db, clock), users)
    await outbox.flush_urgent()
    row = (await _rows(db))[0]
    assert row.status == NotificationStatus.FAILED and row.attempts == 1


async def test_unknown_kind_is_failed_without_sending(
    db: Database, users: UserService, clock: FakeClock
) -> None:
    async with db.transaction() as s:
        await enqueue(s, chat_id=1, kind="nope", payload={}, dedupe_key="k3", now=clock.now(), urgent=True)
    sender = FakeSender()
    await OutboxSender(sender, OutboxStore(db, clock), users).flush_urgent()
    assert sender.sent == []
    assert (await _rows(db))[0].status == NotificationStatus.FAILED


async def test_dedupe_key_and_non_urgent_and_future_rows(
    db: Database, users: UserService, clock: FakeClock
) -> None:
    from datetime import timedelta

    async with db.transaction() as s:
        first = await enqueue(s, chat_id=1, kind="access.rejected", payload={"user_id": 1},
                              dedupe_key="same", now=clock.now(), urgent=True)
        dup = await enqueue(s, chat_id=1, kind="access.rejected", payload={"user_id": 1},
                            dedupe_key="same", now=clock.now(), urgent=True)
        await enqueue(s, chat_id=2, kind="access.rejected", payload={"user_id": 1},
                      dedupe_key="queued", now=clock.now(), urgent=False)
        await enqueue(s, chat_id=3, kind="access.rejected", payload={"user_id": 1},
                      dedupe_key="later", now=clock.now(), urgent=True,
                      scheduled_at=clock.now() + timedelta(hours=1))
    assert first is not None and dup is None

    sender = FakeSender()
    await OutboxSender(sender, OutboxStore(db, clock), users).flush_urgent()
    assert [c for c, _, _ in sender.sent] == [1]  # non-urgent waits for the M5 tick
