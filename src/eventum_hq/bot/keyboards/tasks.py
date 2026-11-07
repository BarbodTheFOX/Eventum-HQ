"""Inline keyboards for tasks. Callback data = action + ids only; the server re-checks."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from eventum_hq.bot import texts
from eventum_hq.bot.formatters import fa_digits, format_minutes, task_button_label, user_label
from eventum_hq.core.jalali import QuickDate
from eventum_hq.models import ApprovalChain, Series, User
from eventum_hq.services.tasks import TaskFilter, TaskRow, TaskView

PAGE_SIZE = 8
TIME_CHOICES = ("10:00", "14:00", "18:00", "22:00")


# ---- callback data -------------------------------------------------------------


class TaskAction(StrEnum):
    OPEN = "o"  # arg=1: edit the current message instead of sending a new one
    START = "s"
    CANCEL_ASK = "c"
    CANCEL_YES = "cy"
    DUE = "d"
    REASSIGN = "r"
    ASSIGN_TO = "a"  # arg = new assignee user id
    HISTORY = "h"
    BRIEF = "b"
    SUBMIT = "sub"
    DONE = "done"
    PHOTOS = "ph"


class TaskCb(CallbackData, prefix="t"):
    action: TaskAction
    task_id: int
    arg: int = 0


class ListScope(StrEnum):
    MY = "my"
    FILTERS = "filters"
    PICK_USER = "pickuser"
    PICK_SERIES = "pickseries"
    OPEN = TaskFilter.OPEN.value
    OVERDUE = TaskFilter.OVERDUE.value
    AT_RISK = TaskFilter.AT_RISK.value
    BY_USER = TaskFilter.BY_USER.value
    BY_SERIES = TaskFilter.BY_SERIES.value


class ListCb(CallbackData, prefix="tl"):
    scope: ListScope
    arg: int = 0
    page: int = 0


class NewTaskStep(StrEnum):
    SKIP_DESCRIPTION = "skip"
    ASSIGNEE = "assignee"
    ESTIMATE = "estimate"  # value = minutes, "0" = no estimate
    SERIES = "series"
    CHAIN = "chain"
    CREATE = "create"
    ABORT = "abort"


class NewTaskCb(CallbackData, prefix="nt"):
    step: NewTaskStep
    value: str = ""


class DateKind(StrEnum):
    QUICK = "q"
    TIME = "t"  # value like "1800" (':' is the callback separator)
    PAST_YES = "py"
    PAST_NO = "pn"


class DateCb(CallbackData, prefix="dt"):
    kind: DateKind
    value: str = ""


# ---- helpers -------------------------------------------------------------------


def _btn(text: str, cb: CallbackData) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=cb.pack())


def _rows(buttons: list[InlineKeyboardButton], per_row: int) -> list[list[InlineKeyboardButton]]:
    return [buttons[i : i + per_row] for i in range(0, len(buttons), per_row)]


def page_slice(items: list, page: int) -> tuple[list, int, int]:  # type: ignore[type-arg]
    """(items on this page, clamped page, page count)."""
    pages = max(1, -(-len(items) // PAGE_SIZE))
    page = min(max(page, 0), pages - 1)
    return items[page * PAGE_SIZE : (page + 1) * PAGE_SIZE], page, pages


# ---- task card -----------------------------------------------------------------


def task_card_keyboard(view: TaskView) -> InlineKeyboardMarkup:
    tid = view.task.id
    rows: list[list[InlineKeyboardButton]] = []
    if view.can_start:
        rows.append([_btn(texts.BTN_START, TaskCb(action=TaskAction.START, task_id=tid))])
    if view.can_submit:
        rows.append([_btn(texts.BTN_SUBMIT, TaskCb(action=TaskAction.SUBMIT, task_id=tid))])
    if view.can_mark_done or view.can_finish:
        label = texts.BTN_FINISH if view.can_finish else texts.BTN_MARK_DONE
        rows.append([_btn(label, TaskCb(action=TaskAction.DONE, task_id=tid))])
    if view.can_send_photos:
        rows.append([_btn(texts.BTN_SEND_COVER_PHOTOS, TaskCb(action=TaskAction.PHOTOS, task_id=tid))])
    if any(i.attachments for i in view.inputs):
        rows.append([_btn(texts.BTN_BRIEF, TaskCb(action=TaskAction.BRIEF, task_id=tid))])
    if view.can_manage:
        rows.append(
            [
                _btn(texts.BTN_CHANGE_DUE, TaskCb(action=TaskAction.DUE, task_id=tid)),
                _btn(texts.BTN_REASSIGN, TaskCb(action=TaskAction.REASSIGN, task_id=tid)),
            ]
        )
        if view.content_item is None:  # reel tasks are cancelled with their reel
            rows.append([_btn(texts.BTN_CANCEL_TASK, TaskCb(action=TaskAction.CANCEL_ASK, task_id=tid))])
    rows.append([_btn(texts.BTN_HISTORY, TaskCb(action=TaskAction.HISTORY, task_id=tid))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_to_card_keyboard(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_btn(texts.BTN_BACK_TO_CARD, TaskCb(action=TaskAction.OPEN, task_id=task_id, arg=1))]]
    )


def cancel_confirm_keyboard(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn(texts.BTN_CONFIRM_CANCEL, TaskCb(action=TaskAction.CANCEL_YES, task_id=task_id)),
                _btn(texts.BTN_KEEP_TASK, TaskCb(action=TaskAction.OPEN, task_id=task_id, arg=1)),
            ]
        ]
    )


def reassign_keyboard(task_id: int, users: list[User], current_assignee_id: int) -> InlineKeyboardMarkup:
    buttons = [
        _btn(user_label(u, with_role=True, html=False), TaskCb(action=TaskAction.ASSIGN_TO, task_id=task_id, arg=u.id))
        for u in users
        if u.id != current_assignee_id
    ]
    rows = _rows(buttons, 1)
    rows.append([_btn(texts.BTN_BACK_TO_CARD, TaskCb(action=TaskAction.OPEN, task_id=task_id, arg=1))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---- lists ---------------------------------------------------------------------


def task_list_keyboard(
    rows_on_page: list[TaskRow],
    now: datetime,
    *,
    scope: ListScope,
    arg: int,
    page: int,
    pages: int,
    with_filters_button: bool,
) -> InlineKeyboardMarkup:
    rows = [
        [_btn(task_button_label(r.task, now), TaskCb(action=TaskAction.OPEN, task_id=r.task.id))]
        for r in rows_on_page
    ]
    if pages > 1:
        nav = []
        if page > 0:
            nav.append(_btn(texts.BTN_PREV, ListCb(scope=scope, arg=arg, page=page - 1)))
        nav.append(
            _btn(
                fa_digits(texts.PAGE_LABEL.format(page=page + 1, pages=pages)),
                ListCb(scope=scope, arg=arg, page=page),
            )
        )
        if page < pages - 1:
            nav.append(_btn(texts.BTN_NEXT, ListCb(scope=scope, arg=arg, page=page + 1)))
        rows.append(nav)
    if with_filters_button:
        rows.append([_btn(texts.BTN_BACK_TO_FILTERS, ListCb(scope=ListScope.FILTERS))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def all_tasks_filters_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn(texts.BTN_FILTER_OPEN, ListCb(scope=ListScope.OPEN))],
            [
                _btn(texts.BTN_FILTER_OVERDUE, ListCb(scope=ListScope.OVERDUE)),
                _btn(texts.BTN_FILTER_AT_RISK, ListCb(scope=ListScope.AT_RISK)),
            ],
            [
                _btn(texts.BTN_FILTER_BY_USER, ListCb(scope=ListScope.PICK_USER)),
                _btn(texts.BTN_FILTER_BY_SERIES, ListCb(scope=ListScope.PICK_SERIES)),
            ],
        ]
    )


def pick_user_keyboard(users: list[User]) -> InlineKeyboardMarkup:
    rows = _rows(
        [_btn(user_label(u, with_role=True, html=False), ListCb(scope=ListScope.BY_USER, arg=u.id)) for u in users], 1
    )
    rows.append([_btn(texts.BTN_BACK_TO_FILTERS, ListCb(scope=ListScope.FILTERS))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pick_series_keyboard(series: list[Series]) -> InlineKeyboardMarkup:
    rows = _rows(
        [_btn(s.name, ListCb(scope=ListScope.BY_SERIES, arg=s.id)) for s in series], 2
    )
    rows.append([_btn(texts.BTN_BACK_TO_FILTERS, ListCb(scope=ListScope.FILTERS))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---- create flow ---------------------------------------------------------------


def _abort_row() -> list[InlineKeyboardButton]:
    return [_btn(texts.BTN_ABORT, NewTaskCb(step=NewTaskStep.ABORT))]


def skip_description_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_btn(texts.BTN_SKIP, NewTaskCb(step=NewTaskStep.SKIP_DESCRIPTION))], _abort_row()]
    )


def new_task_assignee_keyboard(users: list[User]) -> InlineKeyboardMarkup:
    rows = _rows(
        [_btn(user_label(u, with_role=True, html=False), NewTaskCb(step=NewTaskStep.ASSIGNEE, value=str(u.id))) for u in users],
        1,
    )
    rows.append(_abort_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def new_task_estimate_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        _btn(format_minutes(m), NewTaskCb(step=NewTaskStep.ESTIMATE, value=str(m)))
        for m in texts.ESTIMATE_CHOICES
    ]
    rows = _rows(buttons, 3)
    rows.append([_btn(texts.BTN_NO_ESTIMATE, NewTaskCb(step=NewTaskStep.ESTIMATE, value="0"))])
    rows.append(_abort_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def new_task_series_keyboard(series: list[Series]) -> InlineKeyboardMarkup:
    rows = _rows(
        [_btn(s.name, NewTaskCb(step=NewTaskStep.SERIES, value=str(s.id))) for s in series], 2
    )
    rows.append([_btn(texts.BTN_NO_SERIES, NewTaskCb(step=NewTaskStep.SERIES, value="0"))])
    rows.append(_abort_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def new_task_chain_keyboard() -> InlineKeyboardMarkup:
    order = (ApprovalChain.FINAL, ApprovalChain.L1_FINAL, ApprovalChain.NONE)
    rows = [[_btn(texts.CHAIN_LABELS[c], NewTaskCb(step=NewTaskStep.CHAIN, value=c.value))] for c in order]
    rows.append(_abort_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def new_task_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn(texts.BTN_CREATE_TASK, NewTaskCb(step=NewTaskStep.CREATE)),
                _btn(texts.BTN_ABORT, NewTaskCb(step=NewTaskStep.ABORT)),
            ]
        ]
    )


# ---- deadline picker -----------------------------------------------------------


def quick_date_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        _btn(texts.QUICK_DATE_LABELS[q.value], DateCb(kind=DateKind.QUICK, value=q.value)) for q in QuickDate
    ]
    rows = _rows(buttons, 2)
    rows.append(_abort_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def time_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        _btn(fa_digits(t), DateCb(kind=DateKind.TIME, value=t.replace(":", ""))) for t in TIME_CHOICES
    ]
    rows = _rows(buttons, 4)
    rows.append(_abort_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def past_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn(texts.BTN_PAST_YES, DateCb(kind=DateKind.PAST_YES)),
                _btn(texts.BTN_PAST_NO, DateCb(kind=DateKind.PAST_NO)),
            ],
            _abort_row(),
        ]
    )


# ---- M2: delivery / review / team ----------------------------------------------------


class SubmitAction(StrEnum):
    SEND = "send"
    ABORT = "abort"


class SubmitCb(CallbackData, prefix="sb"):
    action: SubmitAction


class ReviewAction(StrEnum):
    OPEN = "o"  # submission_id field carries the task id
    APPROVE = "ok"
    CHANGES = "ch"
    DETAILS = "d"  # submission_id field carries the task id


class ReviewCb(CallbackData, prefix="rv"):
    action: ReviewAction
    submission_id: int
    version: int = 0
    stage: str = ""


class NotesAction(StrEnum):
    DONE = "done"
    ABORT = "abort"


class NotesCb(CallbackData, prefix="rn"):
    action: NotesAction


class TeamAction(StrEnum):
    HOME = "home"
    NEW_DELEGATION = "newdel"
    PICK_DELEGATE = "pick"  # arg = user id
    REVOKE = "revoke"  # arg = delegation id


class TeamCb(CallbackData, prefix="tm"):
    action: TeamAction
    arg: int = 0


def submit_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn(texts.BTN_SEND_FOR_REVIEW, SubmitCb(action=SubmitAction.SEND))],
            [_btn(texts.BTN_ABORT, SubmitCb(action=SubmitAction.ABORT))],
        ]
    )


def notes_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn(texts.BTN_NOTES_DONE, NotesCb(action=NotesAction.DONE))],
            [_btn(texts.BTN_ABORT, NotesCb(action=NotesAction.ABORT))],
        ]
    )


def review_keyboard(task_id: int, submission_id: int, version: int, stage: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn(texts.BTN_APPROVE, ReviewCb(action=ReviewAction.APPROVE, submission_id=submission_id,
                                                 version=version, stage=stage)),
                _btn(texts.BTN_REQUEST_CHANGES, ReviewCb(action=ReviewAction.CHANGES,
                                                         submission_id=submission_id,
                                                         version=version, stage=stage)),
            ],
            [_btn(texts.BTN_DETAILS, ReviewCb(action=ReviewAction.DETAILS, submission_id=task_id))],
        ]
    )


def review_queue_keyboard(rows_on_page: list[TaskRow], now: datetime) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn(task_button_label(r.task, now), ReviewCb(action=ReviewAction.OPEN, submission_id=r.task.id))]
            for r in rows_on_page
        ]
    )


def team_keyboard(*, can_delegate: bool, active_delegation_id: int | None) -> InlineKeyboardMarkup:
    rows = []
    if can_delegate:
        rows.append([_btn(texts.BTN_NEW_DELEGATION, TeamCb(action=TeamAction.NEW_DELEGATION))])
        if active_delegation_id is not None:
            rows.append([_btn(texts.BTN_REVOKE_DELEGATION,
                              TeamCb(action=TeamAction.REVOKE, arg=active_delegation_id))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def delegate_pick_keyboard(users: list[User]) -> InlineKeyboardMarkup:
    rows = [[_btn(user_label(u, with_role=True, html=False), TeamCb(action=TeamAction.PICK_DELEGATE, arg=u.id))]
            for u in users]
    rows.append([_btn(texts.BTN_ABORT, TeamCb(action=TeamAction.HOME))])
    return InlineKeyboardMarkup(inline_keyboard=rows)
