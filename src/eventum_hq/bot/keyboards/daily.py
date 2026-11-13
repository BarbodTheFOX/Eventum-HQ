"""Inline keyboards for 📝 the daily operations report (M7)."""

from __future__ import annotations

from enum import StrEnum

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from eventum_hq.bot import texts


class DailyAction(StrEnum):
    PREVIEW = "p"
    LIST = "l"
    CLEAR_ASK = "ca"
    CLEAR_YES = "cy"
    FINAL = "f"
    ADD = "a"  # back to writing notes


class DailyCb(CallbackData, prefix="dr"):
    action: DailyAction


def _btn(text: str, action: DailyAction) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=DailyCb(action=action).pack())


def daily_home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn(texts.BTN_DAILY_PREVIEW, DailyAction.PREVIEW), _btn(texts.BTN_DAILY_LIST, DailyAction.LIST)],
        [_btn(texts.BTN_DAILY_CLEAR, DailyAction.CLEAR_ASK)],
    ])


def daily_saved_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_btn(texts.BTN_DAILY_PREVIEW, DailyAction.PREVIEW)]])


def daily_preview_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn(texts.BTN_DAILY_FINAL, DailyAction.FINAL), _btn(texts.BTN_DAILY_ADD, DailyAction.ADD)],
    ])


def daily_clear_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn(texts.BTN_DAILY_CLEAR_YES, DailyAction.CLEAR_YES), _btn(texts.BTN_DAILY_BACK, DailyAction.ADD)],
    ])
