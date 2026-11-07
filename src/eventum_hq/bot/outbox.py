"""Delivers outbox rows written by services.

M0 delivers urgent rows right after each update (see ``OutboxFlushMiddleware``)
and once at startup. The periodic tick, quiet hours and backoff retries come in M5.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol

from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove

from eventum_hq.bot import texts
from eventum_hq.bot.formatters import access_request_card, esc, role_label, task_card
from eventum_hq.bot.keyboards.access import access_request_keyboard
from eventum_hq.bot.keyboards.main_menu import main_menu
from eventum_hq.bot.keyboards.tasks import task_card_keyboard
from eventum_hq.core.timeutil import Clock
from eventum_hq.models import Notification
from eventum_hq.services import tasks as task_kinds
from eventum_hq.services import users as user_kinds
from eventum_hq.services.notifications import OutboxStore
from eventum_hq.services.tasks import TaskService
from eventum_hq.services.users import UserService

log = logging.getLogger(__name__)

Markup = InlineKeyboardMarkup | ReplyKeyboardMarkup | ReplyKeyboardRemove | None


class MessageSender(Protocol):
    async def send_message(self, chat_id: int, text: str, **kwargs: Any) -> Any: ...


class UnknownNotificationKind(Exception):
    pass


_TASK_CARD_KINDS = {task_kinds.KIND_TASK_ASSIGNED, task_kinds.KIND_TASK_DUE_CHANGED}


class UndeliverableNotification(Exception):
    """The notification no longer makes sense (e.g. recipient lost access)."""


async def render(
    row: Notification,
    users: UserService,
    tasks: TaskService | None = None,
    clock: Clock | None = None,
) -> tuple[str, Markup]:
    payload = row.payload or {}
    if row.kind in _TASK_CARD_KINDS:
        if tasks is None or clock is None:
            raise UnknownNotificationKind(row.kind)
        recipient = await users.get(int(payload["user_id"]))
        if recipient is None or not recipient.can_use_bot:
            raise UndeliverableNotification("recipient inactive")
        view = await tasks.get_view(recipient, task_id=int(payload["task_id"]))
        prefix = (
            texts.NOTIFY_TASK_ASSIGNED
            if row.kind == task_kinds.KIND_TASK_ASSIGNED
            else texts.NOTIFY_TASK_DUE_CHANGED
        )
        return prefix + task_card(view, clock.now()), task_card_keyboard(view)
    if row.kind == task_kinds.KIND_TASK_UNASSIGNED:
        return texts.NOTIFY_TASK_UNASSIGNED.format(
            code=esc(payload["code"]), title=esc(payload["title"])
        ), None
    if row.kind == task_kinds.KIND_TASK_CANCELLED:
        return texts.NOTIFY_TASK_CANCELLED.format(
            code=esc(payload["code"]), title=esc(payload["title"])
        ), None
    if row.kind == user_kinds.KIND_ACCESS_REQUEST:
        requested_role = payload["requested_role"]
        text = access_request_card(
            full_name=payload.get("full_name"),
            username=payload.get("username"),
            telegram_id=int(payload["telegram_id"]),
            role=requested_role,
        )
        return text, access_request_keyboard(int(payload["user_id"]), requested_role)
    if row.kind == user_kinds.KIND_ACCESS_APPROVED:
        user = await users.get(int(payload["user_id"]))
        if user is None or not user.can_use_bot:
            raise UnknownNotificationKind("approved user is no longer active")
        return texts.ACCESS_APPROVED_FOR_USER.format(role=role_label(user.role)), main_menu(user)
    if row.kind == user_kinds.KIND_ACCESS_REJECTED:
        return texts.ACCESS_REJECTED_FOR_USER, ReplyKeyboardRemove()
    raise UnknownNotificationKind(row.kind)


class OutboxSender:
    def __init__(
        self,
        sender: MessageSender,
        store: OutboxStore,
        users: UserService,
        tasks: TaskService | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._sender = sender
        self._store = store
        self._users = users
        self._tasks = tasks
        self._clock = clock
        self._lock = asyncio.Lock()  # never deliver the same row twice in parallel

    async def flush_urgent(self) -> int:
        """Send every due urgent row. Returns the number sent successfully."""
        sent = 0
        async with self._lock:
            for row in await self._store.due_urgent():
                if await self._deliver(row):
                    sent += 1
        return sent

    async def _deliver(self, row: Notification) -> bool:
        try:
            text, markup = await render(row, self._users, self._tasks, self._clock)
        except Exception as exc:  # broken payload / unknown kind: do not retry
            log.exception("outbox render failed id=%s kind=%s", row.id, row.kind)
            await self._store.mark_failed(row.id, f"render: {exc!r}", permanent=True)
            return False

        try:
            await self._sender.send_message(row.chat_id, text, reply_markup=markup)
        except TelegramRetryAfter as exc:
            log.warning("outbox rate-limited id=%s retry_after=%s", row.id, exc.retry_after)
            await self._store.mark_failed(row.id, f"retry_after={exc.retry_after}")
            return False
        except (TelegramForbiddenError, TelegramBadRequest) as exc:
            # user blocked the bot / chat not found: retrying will not help
            log.warning("outbox permanent failure id=%s kind=%s: %s", row.id, row.kind, exc)
            await self._store.mark_failed(row.id, repr(exc), permanent=True)
            return False
        except Exception as exc:
            log.exception("outbox send failed id=%s kind=%s", row.id, row.kind)
            await self._store.mark_failed(row.id, repr(exc))
            return False

        await self._store.mark_sent(row.id)
        log.info("outbox sent id=%s kind=%s", row.id, row.kind)
        return True
