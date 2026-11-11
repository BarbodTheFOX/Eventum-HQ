"""Middlewares on outgoing Bot API requests (``bot.session.middleware``).

Telegram only accepts ``answerCallbackQuery`` for about 15 seconds after the
button press. When the VPN lags, the press reaches the bot later than that and
the answer fails with "query is too old". The answer is only the little
loading spinner on the button, so this is harmless: log a warning and let the
handler carry on instead of aborting the user's action with a traceback.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import AnswerCallbackQuery

if TYPE_CHECKING:
    from aiogram import Bot
    from aiogram.client.session.middlewares.base import NextRequestMiddlewareType
    from aiogram.methods import TelegramMethod

log = logging.getLogger(__name__)

_EXPIRED_MARKERS = ("query is too old", "query id is invalid")


def is_expired_callback_answer(exc: TelegramBadRequest) -> bool:
    text = (exc.message or "").lower()
    return any(marker in text for marker in _EXPIRED_MARKERS)


class IgnoreExpiredCallbackAnswer(BaseRequestMiddleware):
    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[Any],
        bot: Bot,
        method: TelegramMethod[Any],
    ) -> Any:
        try:
            return await make_request(bot, method)
        except TelegramBadRequest as exc:
            if isinstance(method, AnswerCallbackQuery) and is_expired_callback_answer(exc):
                log.warning("callback answer expired (slow network?) — ignored")
                return True
            raise
