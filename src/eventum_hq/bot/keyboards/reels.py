"""Inline keyboards for reels. Callback data = action + ids only; the server re-checks."""

from __future__ import annotations

from enum import StrEnum

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from eventum_hq.bot import texts
from eventum_hq.bot.formatters import format_minutes, user_label
from eventum_hq.bot.keyboards.tasks import TaskAction, TaskCb
from eventum_hq.models import Series, User
from eventum_hq.services.reels import ReelView


class ReelStep(StrEnum):
    SUBTYPE = "sub"
    EDIT_TYPE = "et"
    SERIES = "ser"  # value = series id, "0" = none
    EDIT_ASSIGNEE = "ea"
    COVER_ASSIGNEE = "ca"
    CREATE = "create"
    ABORT = "abort"
    DEADLINES = "dls"  # show which deadline to change
    DEADLINE = "dl"  # value = photos | edit | cover
    ESTIMATES = "ests"
    ESTIMATE_KEY = "ek"  # value = edit | cover
    ESTIMATE = "est"  # value = minutes
    BACK = "back"


class ReelCb(CallbackData, prefix="nr"):
    step: ReelStep
    value: str = ""


class ReelAction(StrEnum):
    OPEN = "o"
    CANCEL_ASK = "c"
    CANCEL_YES = "cy"
    PUBLISH = "p"


class ReelCardCb(CallbackData, prefix="rl"):
    action: ReelAction
    item_id: int


class PhotosAction(StrEnum):
    DONE = "done"
    ABORT = "abort"


class PhotosCb(CallbackData, prefix="ph"):
    action: PhotosAction


class PublishAction(StrEnum):
    NOW = "now"
    OTHER_TIME = "other"
    ABORT = "abort"


class PublishCb(CallbackData, prefix="pb"):
    action: PublishAction


def _btn(text: str, cb: CallbackData) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=cb.pack())


def _abort() -> list[InlineKeyboardButton]:
    return [_btn(texts.BTN_ABORT, ReelCb(step=ReelStep.ABORT))]


def subtype_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn(texts.SUBTYPE_LABELS["NORMAL"], ReelCb(step=ReelStep.SUBTYPE, value="NORMAL")),
         _btn(texts.SUBTYPE_LABELS["TRIAL"], ReelCb(step=ReelStep.SUBTYPE, value="TRIAL"))],
        _abort(),
    ])


def edit_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn(texts.BTN_EDIT_NORMAL, ReelCb(step=ReelStep.EDIT_TYPE, value="normal")),
         _btn(texts.BTN_EDIT_MOTION, ReelCb(step=ReelStep.EDIT_TYPE, value="motion"))],
        _abort(),
    ])


def series_keyboard(series: list[Series], default_id: int | None) -> InlineKeyboardMarkup:
    ordered = sorted(series, key=lambda s: s.id != default_id)
    buttons = [
        _btn((texts.DEFAULT_MARK if s.id == default_id else "") + s.name, ReelCb(step=ReelStep.SERIES, value=str(s.id)))
        for s in ordered
    ]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    rows.append([_btn(texts.BTN_NO_SERIES, ReelCb(step=ReelStep.SERIES, value="0"))])
    rows.append(_abort())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def assignee_keyboard(users: list[User], default_id: int | None, step: ReelStep) -> InlineKeyboardMarkup:
    ordered = sorted(users, key=lambda u: u.id != default_id)
    rows = [
        [_btn((texts.DEFAULT_MARK if u.id == default_id else "") + user_label(u, with_role=True, html=False),
              ReelCb(step=step, value=str(u.id)))]
        for u in ordered
    ]
    rows.append(_abort())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn(texts.BTN_CREATE_REEL, ReelCb(step=ReelStep.CREATE))],
        [_btn(texts.BTN_CHANGE_DEADLINES, ReelCb(step=ReelStep.DEADLINES)),
         _btn(texts.BTN_CHANGE_ESTIMATES, ReelCb(step=ReelStep.ESTIMATES))],
        _abort(),
    ])


def deadline_pick_keyboard() -> InlineKeyboardMarkup:
    rows = [[_btn(label, ReelCb(step=ReelStep.DEADLINE, value=key))] for key, label in texts.DEADLINE_KEY_LABELS.items()]
    rows.append([_btn(texts.BTN_BACK, ReelCb(step=ReelStep.BACK))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def estimate_key_keyboard() -> InlineKeyboardMarkup:
    rows = [[_btn(texts.DEADLINE_KEY_LABELS[key], ReelCb(step=ReelStep.ESTIMATE_KEY, value=key))]
            for key in ("edit", "cover")]
    rows.append([_btn(texts.BTN_BACK, ReelCb(step=ReelStep.BACK))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def estimate_keyboard() -> InlineKeyboardMarkup:
    buttons = [_btn(format_minutes(m), ReelCb(step=ReelStep.ESTIMATE, value=str(m))) for m in texts.ESTIMATE_CHOICES]
    rows = [buttons[i : i + 3] for i in range(0, len(buttons), 3)]
    rows.append([_btn(texts.BTN_BACK, ReelCb(step=ReelStep.BACK))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reel_card_keyboard(view: ReelView) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    task_row = []
    if view.edit_task is not None:
        task_row.append(_btn(texts.BTN_OPEN_EDIT, TaskCb(action=TaskAction.OPEN, task_id=view.edit_task.id)))
    if view.cover_task is not None:
        task_row.append(_btn(texts.BTN_OPEN_COVER, TaskCb(action=TaskAction.OPEN, task_id=view.cover_task.id)))
    if task_row:
        rows.append(task_row)
    if view.can_publish:
        rows.append([_btn(texts.BTN_PUBLISH, ReelCardCb(action=ReelAction.PUBLISH, item_id=view.item.id))])
    if view.can_cancel:
        rows.append([_btn(texts.BTN_CANCEL_REEL, ReelCardCb(action=ReelAction.CANCEL_ASK, item_id=view.item.id))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reel_cancel_confirm_keyboard(item_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        _btn(texts.BTN_CONFIRM_CANCEL, ReelCardCb(action=ReelAction.CANCEL_YES, item_id=item_id)),
        _btn(texts.BTN_KEEP_TASK, ReelCardCb(action=ReelAction.OPEN, item_id=item_id)),
    ]])


def ready_list_keyboard(views: list[ReelView]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn(f"🚀 {v.item.code} · {v.item.title[:30]}", ReelCardCb(action=ReelAction.OPEN, item_id=v.item.id))]
        for v in views
    ])


def photos_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn(texts.BTN_NOTES_DONE, PhotosCb(action=PhotosAction.DONE))],
        [_btn(texts.BTN_ABORT, PhotosCb(action=PhotosAction.ABORT))],
    ])


def publish_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn(texts.BTN_PUBLISH_NOW, PublishCb(action=PublishAction.NOW))],
        [_btn(texts.BTN_PUBLISH_OTHER_TIME, PublishCb(action=PublishAction.OTHER_TIME))],
        [_btn(texts.BTN_ABORT, PublishCb(action=PublishAction.ABORT))],
    ])
