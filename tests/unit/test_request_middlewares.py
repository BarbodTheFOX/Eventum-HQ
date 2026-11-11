"""An expired callback answer (slow network) must not abort the handler."""

from __future__ import annotations

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import AnswerCallbackQuery, SendMessage

from eventum_hq.bot.request_middlewares import IgnoreExpiredCallbackAnswer

TOO_OLD = "Bad Request: query is too old and response timeout expired or query ID is invalid"


def _raising(method, message: str):
    async def make_request(bot, m):
        raise TelegramBadRequest(method=method, message=message)

    return make_request


async def test_expired_callback_answer_is_ignored() -> None:
    method = AnswerCallbackQuery(callback_query_id="1")
    result = await IgnoreExpiredCallbackAnswer()(_raising(method, TOO_OLD), None, method)
    assert result is True


async def test_other_callback_answer_errors_still_raise() -> None:
    method = AnswerCallbackQuery(callback_query_id="1")
    with pytest.raises(TelegramBadRequest):
        await IgnoreExpiredCallbackAnswer()(_raising(method, "Bad Request: message is too long"), None, method)


async def test_same_text_on_other_methods_still_raises() -> None:
    method = SendMessage(chat_id=1, text="x")
    with pytest.raises(TelegramBadRequest):
        await IgnoreExpiredCallbackAnswer()(_raising(method, TOO_OLD), None, method)


async def test_successful_requests_pass_through() -> None:
    method = AnswerCallbackQuery(callback_query_id="1")

    async def make_request(bot, m):
        return "ok"

    assert await IgnoreExpiredCallbackAnswer()(make_request, None, method) == "ok"
