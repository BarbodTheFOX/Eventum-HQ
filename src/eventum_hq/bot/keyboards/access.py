"""Inline keyboard for the OWNER's access-request card."""

from __future__ import annotations

from enum import StrEnum

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from eventum_hq.bot import texts


class AccessAction(StrEnum):
    APPROVE = "ok"
    REJECT = "no"


class AccessCb(CallbackData, prefix="acc"):
    """Only action + id. The server re-checks permission and state from the DB."""

    action: AccessAction
    user_id: int


def access_request_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BTN_APPROVE_AS_MEMBER,
                    callback_data=AccessCb(action=AccessAction.APPROVE, user_id=user_id).pack(),
                ),
                InlineKeyboardButton(
                    text=texts.BTN_REJECT,
                    callback_data=AccessCb(action=AccessAction.REJECT, user_id=user_id).pack(),
                ),
            ]
        ]
    )
