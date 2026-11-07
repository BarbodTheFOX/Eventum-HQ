"""Update-level middlewares.

* ``AccessMiddleware`` — whitelist (handoff §3.3, §6.3): in private chats only
  approved + active users get through; unknown/inactive users may only send
  /start. Nothing from groups or channels is handled (except the bot's own
  membership changes, so it can leave foreign groups).
* ``OutboxFlushMiddleware`` — after every update, deliver urgent outbox rows
  that the handler's service call just committed.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, TelegramObject, Update

from eventum_hq.bot import texts

from eventum_hq.bot.keyboards.access import JOIN_PREFIX
from eventum_hq.bot.keyboards.main_menu import AdminViews
from eventum_hq.bot.outbox import OutboxSender
from eventum_hq.core.timeutil import Clock
from eventum_hq.services.delegations import DelegationService
from eventum_hq.services.users import UserService

log = logging.getLogger(__name__)

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]

_START_RE = re.compile(r"^/start(@\w+)?(\s|$)", re.IGNORECASE)


def is_start_command(text: str | None) -> bool:
    return bool(text) and _START_RE.match(text.strip()) is not None  # type: ignore[union-attr]


def is_join_callback(data: str | None) -> bool:
    """The role-picker buttons an unknown user presses to ask for access."""
    return bool(data) and data.startswith(f"{JOIN_PREFIX}:")  # type: ignore[union-attr]


def is_allowed(*, chat_type: str | None, is_known_user: bool, is_entry: bool) -> bool:
    """Pure gate decision (unit-tested). ``is_entry`` = /start or a role-picker button."""
    if chat_type != "private":
        return False
    return is_known_user or is_entry


def should_leave_chat(*, chat_type: str, chat_id: int, team_group_id: int | None) -> bool:
    """The bot only stays in the configured team group."""
    if chat_type not in ("group", "supergroup"):
        return False
    return team_group_id is None or chat_id != team_group_id


class AccessMiddleware(BaseMiddleware):
    def __init__(
        self,
        users: UserService,
        delegations: DelegationService | None = None,
        views: AdminViews | None = None,
    ) -> None:
        self._users = users
        self._delegations = delegations
        self._views = views

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        assert isinstance(event, Update)
        if event.my_chat_member is not None:
            return await handler(event, data)

        chat = data.get("event_chat")
        tg_user = data.get("event_from_user")
        if chat is None or tg_user is None or tg_user.is_bot:
            return None

        current_user = None
        if chat.type == "private":
            current_user = await self._users.get_active_by_telegram_id(tg_user.id)

        text = event.message.text if event.message is not None else None
        cb_data = event.callback_query.data if event.callback_query is not None else None
        if not is_allowed(
            chat_type=chat.type,
            is_known_user=current_user is not None,
            is_entry=is_start_command(text) or is_join_callback(cb_data),
        ):
            if event.callback_query is not None and chat.type == "private":
                await event.callback_query.answer()  # stop the spinner, say nothing
            log.debug("update dropped chat_type=%s known=%s", chat.type, current_user is not None)
            return None

        data["current_user"] = current_user
        if current_user is not None and self._delegations is not None and self._views is not None:
            self._views.set_delegate(
                current_user.telegram_id,
                await self._delegations.is_active_delegate(current_user.id),
            )
        return await handler(event, data)


class OutboxFlushMiddleware(BaseMiddleware):
    def __init__(self, outbox: OutboxSender) -> None:
        self._outbox = outbox

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        try:
            return await handler(event, data)
        finally:
            try:
                await self._outbox.flush_urgent()
            except Exception:
                log.exception("urgent outbox flush failed")


FLOW_TIMEOUT = timedelta(minutes=30)
_TOUCHED_KEY = "_touched"


class FlowTimeoutMiddleware(BaseMiddleware):
    """Unfinished flows (FSM states) expire after 30 minutes without activity (§5.1).

    Registered on messages and callback queries. Before the handler: if the
    current flow is too old, clear it and tell the user. After the handler: if
    a flow is (still) active, remember "now" as its last activity.
    """

    def __init__(self, clock: Clock, timeout: timedelta = FLOW_TIMEOUT) -> None:
        self._clock = clock
        self._timeout = timeout

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        state: FSMContext | None = data.get("state")
        if state is not None and await state.get_state() is not None:
            touched = (await state.get_data()).get(_TOUCHED_KEY)
            now = self._clock.now().timestamp()
            if touched is not None and now - float(touched) > self._timeout.total_seconds():
                await state.clear()
                # state filters read this cached value, not the storage
                data["raw_state"] = None
                if isinstance(event, Message):
                    await event.answer(texts.FLOW_EXPIRED)
                elif isinstance(event, CallbackQuery) and isinstance(event.message, Message):
                    await event.message.answer(texts.FLOW_EXPIRED)
        result = await handler(event, data)
        if state is not None and await state.get_state() is not None:
            await state.update_data({_TOUCHED_KEY: self._clock.now().timestamp()})
        return result
