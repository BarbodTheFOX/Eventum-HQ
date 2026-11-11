"""Inline keyboards for 🔁 recurring tasks (F10), opened from 👥 تیم."""

from __future__ import annotations

from enum import StrEnum

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from eventum_hq.bot import texts
from eventum_hq.bot.formatters import format_minutes, user_label
from eventum_hq.bot.keyboards.tasks import TeamAction, TeamCb
from eventum_hq.models import ApprovalChain, User
from eventum_hq.services.recurrences import RecurrenceRow

CREATE_TIME_CHOICES = ("08:00", "08:30", "09:00", "10:00")
DUE_TIME_CHOICES = ("12:00", "14:00", "18:00", "22:00")


class RecurAction(StrEnum):
    LIST = "list"
    NEW = "new"
    STOP = "stop"  # arg = recurrence id
    ASSIGNEE = "who"  # arg = user id
    RULE = "rule"  # value = DAILY / WEEKDAYS
    DAY = "day"  # arg = weekday (0 = Saturday), toggles
    DAYS_DONE = "days"
    CREATE_TIME = "ct"  # value = HHMM
    DUE_TIME = "dt"  # value = HHMM
    CHAIN = "chain"  # value = ApprovalChain
    ESTIMATE = "est"  # arg = minutes, 0 = none
    CREATE = "create"
    ABORT = "abort"


class RecurCb(CallbackData, prefix="rc"):
    action: RecurAction
    arg: int = 0
    value: str = ""


def _btn(text: str, cb: CallbackData) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=cb.pack())


def _abort_row() -> list[InlineKeyboardButton]:
    return [_btn(texts.BTN_ABORT, RecurCb(action=RecurAction.ABORT))]


def recurrences_button_row() -> list[InlineKeyboardButton]:
    return [_btn(texts.BTN_RECURRENCES, RecurCb(action=RecurAction.LIST))]


def recurrence_list_keyboard(rows: list[RecurrenceRow]) -> InlineKeyboardMarkup:
    buttons = [[_btn(texts.BTN_NEW_RECURRENCE, RecurCb(action=RecurAction.NEW))]]
    for row in rows:
        title = row.recurrence.title if len(row.recurrence.title) <= 30 else row.recurrence.title[:29] + "…"
        buttons.append([_btn(texts.BTN_STOP_RECURRENCE.format(title=title),
                             RecurCb(action=RecurAction.STOP, arg=row.recurrence.id))])
    buttons.append([_btn(texts.BTN_BACK_TO_TEAM, TeamCb(action=TeamAction.HOME))])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def assignee_keyboard(users: list[User]) -> InlineKeyboardMarkup:
    rows = [[_btn(user_label(u, with_role=True, html=False), RecurCb(action=RecurAction.ASSIGNEE, arg=u.id))]
            for u in users]
    rows.append(_abort_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def rule_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn(texts.BTN_RULE_DAILY, RecurCb(action=RecurAction.RULE, value="DAILY"))],
        [_btn(texts.BTN_RULE_WEEKDAYS, RecurCb(action=RecurAction.RULE, value="WEEKDAYS"))],
        _abort_row(),
    ])


def weekdays_keyboard(selected: set[int]) -> InlineKeyboardMarkup:
    days = [_btn(("✅ " if d in selected else "") + texts.WEEKDAYS[d], RecurCb(action=RecurAction.DAY, arg=d))
            for d in range(7)]
    rows = [days[i:i + 3] for i in range(0, 7, 3)]
    rows.append([_btn(texts.BTN_WEEKDAYS_DONE, RecurCb(action=RecurAction.DAYS_DONE))])
    rows.append(_abort_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def time_choice_keyboard(action: RecurAction, choices: tuple[str, ...]) -> InlineKeyboardMarkup:
    row = [_btn(c, RecurCb(action=action, value=c.replace(":", ""))) for c in choices]
    return InlineKeyboardMarkup(inline_keyboard=[row, _abort_row()])


def chain_keyboard() -> InlineKeyboardMarkup:
    order = (ApprovalChain.FINAL, ApprovalChain.L1_FINAL, ApprovalChain.NONE)
    rows = [[_btn(texts.CHAIN_LABELS[c], RecurCb(action=RecurAction.CHAIN, value=c.value))] for c in order]
    rows.append(_abort_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def estimate_keyboard() -> InlineKeyboardMarkup:
    buttons = [_btn(format_minutes(m), RecurCb(action=RecurAction.ESTIMATE, arg=m)) for m in texts.ESTIMATE_CHOICES]
    rows = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]
    rows.append([_btn(texts.BTN_NO_ESTIMATE, RecurCb(action=RecurAction.ESTIMATE, arg=0))])
    rows.append(_abort_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        _btn(texts.BTN_CREATE_RECURRENCE, RecurCb(action=RecurAction.CREATE)),
        _btn(texts.BTN_ABORT, RecurCb(action=RecurAction.ABORT)),
    ]])
