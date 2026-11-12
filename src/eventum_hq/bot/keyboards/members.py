"""Inline keyboards for 👤 team members and offboarding (F15, M6), opened from 👥 تیم."""

from __future__ import annotations

from enum import StrEnum

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from eventum_hq.bot import texts
from eventum_hq.bot.formatters import fa_digits, role_label, user_label
from eventum_hq.bot.keyboards.tasks import TeamAction, TeamCb
from eventum_hq.models import User
from eventum_hq.services.offboarding import MemberRow, MemberView

TITLE_MAX = 28


class MemberAction(StrEnum):
    LIST = "list"
    HANDOVERS = "hand"
    OPEN = "o"  # arg = user id
    DEACT_ASK = "da"  # arg = user id
    DEACT_YES = "dy"  # arg = user id
    ALL_PICK = "ap"  # arg = from user id
    ALL_TO = "at"  # arg = from user id, to = target
    TASK_PICK = "tp"  # arg = task id, back = owner id
    TASK_TO = "tt"  # arg = task id, to = target, back = owner id
    REC_PICK = "rp"  # arg = recurrence id, back = owner id
    REC_TO = "rt"  # arg = recurrence id, to = target, back = owner id


class MemberCb(CallbackData, prefix="mb"):
    action: MemberAction
    arg: int = 0
    to: int = 0
    back: int = 0


def _btn(text: str, cb: CallbackData) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=cb.pack())


def _short(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= TITLE_MAX else text[: TITLE_MAX - 1] + "…"


def team_members_rows(pending_handovers: int) -> list[list[InlineKeyboardButton]]:
    rows = [[_btn(texts.BTN_MEMBERS, MemberCb(action=MemberAction.LIST))]]
    if pending_handovers:
        rows.append([_btn(texts.BTN_HANDOVERS.format(count=fa_digits(pending_handovers)),
                          MemberCb(action=MemberAction.HANDOVERS))])
    return rows


def _back_to_team() -> list[InlineKeyboardButton]:
    return [_btn(texts.BTN_BACK_TO_TEAM, TeamCb(action=TeamAction.HOME))]


def members_keyboard(rows: list[MemberRow]) -> InlineKeyboardMarkup:
    buttons = [
        [_btn(texts.MEMBER_BUTTON.format(name=user_label(r.user, html=False), role=role_label(r.user.role),
                                         open=fa_digits(r.open_tasks)),
              MemberCb(action=MemberAction.OPEN, arg=r.user.id))]
        for r in rows
    ]
    buttons.append(_back_to_team())
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _back_to_members() -> list[InlineKeyboardButton]:
    return [_btn(texts.BTN_BACK_TO_MEMBERS, MemberCb(action=MemberAction.LIST))]


def member_keyboard(view: MemberView) -> InlineKeyboardMarkup:
    uid = view.user.id
    rows: list[list[InlineKeyboardButton]] = []
    if view.can_deactivate:
        rows.append([_btn(texts.BTN_DEACTIVATE, MemberCb(action=MemberAction.DEACT_ASK, arg=uid))])
    if not view.user.is_active:
        if view.open_tasks:
            rows.append([_btn(texts.BTN_TRANSFER_ALL, MemberCb(action=MemberAction.ALL_PICK, arg=uid))])
        for task in view.open_tasks:
            rows.append([_btn(texts.BTN_TRANSFER_TASK.format(code=task.code, title=_short(task.title)),
                              MemberCb(action=MemberAction.TASK_PICK, arg=task.id, back=uid))])
        for recurrence in view.recurrences:
            rows.append([_btn(texts.BTN_TRANSFER_REC.format(title=_short(recurrence.title)),
                              MemberCb(action=MemberAction.REC_PICK, arg=recurrence.id, back=uid))])
    rows.append(_back_to_members())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def deactivate_confirm_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn(texts.BTN_DEACTIVATE_YES, MemberCb(action=MemberAction.DEACT_YES, arg=user_id))],
        [_btn(texts.BTN_BACK, MemberCb(action=MemberAction.OPEN, arg=user_id))],
    ])


def pick_target_keyboard(users: list[User], action: MemberAction, arg: int, back: int) -> InlineKeyboardMarkup:
    rows = [[_btn(user_label(u, with_role=True, html=False), MemberCb(action=action, arg=arg, to=u.id, back=back))]
            for u in users]
    rows.append([_btn(texts.BTN_BACK, MemberCb(action=MemberAction.OPEN, arg=back))])
    return InlineKeyboardMarkup(inline_keyboard=rows)
