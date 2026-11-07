"""Inline keyboards for the access flow.

* ``JoinCb``  — the applicant picks a role (allowed for unknown users).
* ``AccessCb`` — the OWNER's card: approve as requested / pick another role / reject.

Callback data holds only an action, an id and a role name. The server
re-validates everything from the DB.
"""

from __future__ import annotations

from enum import StrEnum

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from eventum_hq.bot import texts
from eventum_hq.bot.formatters import role_label
from eventum_hq.models import Role
from eventum_hq.services.permissions import SELECTABLE_ROLES

JOIN_PREFIX = "join"


class JoinCb(CallbackData, prefix=JOIN_PREFIX):
    role: str


class AccessAction(StrEnum):
    APPROVE = "ok"  # approve with the role the user asked for (read from DB)
    PICK_ROLE = "pick"  # show role buttons
    BACK = "back"  # back to the main card buttons
    APPROVE_AS = "as"  # approve with ``role``
    REJECT = "no"


class AccessCb(CallbackData, prefix="acc"):
    action: AccessAction
    user_id: int
    role: str = ""


def _two_per_row(buttons: list[InlineKeyboardButton]) -> list[list[InlineKeyboardButton]]:
    return [buttons[i : i + 2] for i in range(0, len(buttons), 2)]


def join_role_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text=role_label(role), callback_data=JoinCb(role=role.value).pack())
        for role in SELECTABLE_ROLES
    ]
    return InlineKeyboardMarkup(inline_keyboard=_two_per_row(buttons))


def access_request_keyboard(user_id: int, requested_role: Role | str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BTN_APPROVE_AS.format(role=role_label(requested_role)),
                    callback_data=AccessCb(action=AccessAction.APPROVE, user_id=user_id).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=texts.BTN_APPROVE_OTHER_ROLE,
                    callback_data=AccessCb(action=AccessAction.PICK_ROLE, user_id=user_id).pack(),
                ),
                InlineKeyboardButton(
                    text=texts.BTN_REJECT,
                    callback_data=AccessCb(action=AccessAction.REJECT, user_id=user_id).pack(),
                ),
            ],
        ]
    )


def access_pick_role_keyboard(user_id: int) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=role_label(role),
            callback_data=AccessCb(
                action=AccessAction.APPROVE_AS, user_id=user_id, role=role.value
            ).pack(),
        )
        for role in SELECTABLE_ROLES
    ]
    rows = _two_per_row(buttons)
    rows.append(
        [
            InlineKeyboardButton(
                text=texts.BTN_BACK,
                callback_data=AccessCb(action=AccessAction.BACK, user_id=user_id).pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
