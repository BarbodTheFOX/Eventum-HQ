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
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from eventum_hq.bot.outbox import OutboxSender
from eventum_hq.services.users import UserService

log = logging.getLogger(__name__)

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]

_START_RE = re.compile(r"^/start(@\w+)?(\s|$)", re.IGNORECASE)


def is_start_command(text: str | None) -> bool:
    return bool(text) and _START_RE.match(text.strip()) is not None  # type: ignore[union-attr]


def is_allowed(*, chat_type: str | None, is_known_user: bool, is_start: bool) -> bool:
    """Pure gate decision (unit-tested)."""
    if chat_type != "private":
        return False
    return is_known_user or is_start


def should_leave_chat(*, chat_type: str, chat_id: int, team_group_id: int | None) -> bool:
    """The bot only stays in the configured team group."""
    if chat_type not in ("group", "supergroup"):
        return False
    return team_group_id is None or chat_id != team_group_id


class AccessMiddleware(BaseMiddleware):
    def __init__(self, users: UserService) -> None:
        self._users = users

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
        if not is_allowed(
            chat_type=chat.type,
            is_known_user=current_user is not None,
            is_start=is_start_command(text),
        ):
            if event.callback_query is not None and chat.type == "private":
                await event.callback_query.answer()  # stop the spinner, say nothing
            log.debug("update dropped chat_type=%s known=%s", chat.type, current_user is not None)
            return None

        data["current_user"] = current_user
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
