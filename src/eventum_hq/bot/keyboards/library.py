"""Inline keyboards for 📚 the library (F9, M4)."""

from __future__ import annotations

from enum import StrEnum

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from eventum_hq.bot import texts
from eventum_hq.bot.formatters import fa_digits
from eventum_hq.models import Series
from eventum_hq.services.outputs import LibraryKind, OutputRow

BUTTON_TITLE_MAX = 32


class LibAction(StrEnum):
    HOME = "h"
    RECENT = "r"
    KIND = "k"  # kind = LibraryKind
    PICK_SERIES = "ps"
    SERIES = "s"  # arg = series id
    QUERY = "q"  # the query text lives in FSM data (callback data is limited to 64 bytes)
    OPEN = "o"  # item = output id; src/kind/arg/page = the list it was opened from


LIST_ACTIONS = (LibAction.RECENT, LibAction.KIND, LibAction.SERIES, LibAction.QUERY)


class LibCb(CallbackData, prefix="lb"):
    action: LibAction
    kind: str = ""
    arg: int = 0
    page: int = 0
    item: int = 0
    src: str = ""


def _btn(text: str, cb: CallbackData) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=cb.pack())


def _home_row() -> list[InlineKeyboardButton]:
    return [_btn(texts.BTN_LIB_HOME, LibCb(action=LibAction.HOME))]


def library_home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn(texts.BTN_LIB_RECENT, LibCb(action=LibAction.RECENT))],
        [
            _btn(texts.BTN_LIB_KIND_REEL, LibCb(action=LibAction.KIND, kind=LibraryKind.REEL.value)),
            _btn(texts.BTN_LIB_KIND_COVER, LibCb(action=LibAction.KIND, kind=LibraryKind.COVER.value)),
            _btn(texts.BTN_LIB_KIND_OTHER, LibCb(action=LibAction.KIND, kind=LibraryKind.OTHER.value)),
        ],
        [_btn(texts.BTN_LIB_BY_SERIES, LibCb(action=LibAction.PICK_SERIES))],
    ])


def library_series_keyboard(series: list[Series]) -> InlineKeyboardMarkup:
    buttons = [_btn(s.name, LibCb(action=LibAction.SERIES, arg=s.id)) for s in series]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append(_home_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def output_button_label(row: OutputRow) -> str:
    title = row.output.title.strip()
    if len(title) > BUTTON_TITLE_MAX:
        title = title[: BUTTON_TITLE_MAX - 1] + "…"
    icon = texts.LIB_TYPE_ICONS.get(str(row.output.output_type), "📄")
    return f"{icon} {row.task_code} · {title}"


def library_list_keyboard(
    rows_on_page: list[OutputRow], *, action: LibAction, kind: str, arg: int, page: int, pages: int
) -> InlineKeyboardMarkup:
    rows = [
        [_btn(output_button_label(r), LibCb(action=LibAction.OPEN, item=r.output.id, src=action.value,
                                            kind=kind, arg=arg, page=page))]
        for r in rows_on_page
    ]
    if pages > 1:
        nav = []
        if page > 0:
            nav.append(_btn(texts.BTN_PREV, LibCb(action=action, kind=kind, arg=arg, page=page - 1)))
        nav.append(_btn(fa_digits(texts.PAGE_LABEL.format(page=page + 1, pages=pages)),
                        LibCb(action=action, kind=kind, arg=arg, page=page)))
        if page < pages - 1:
            nav.append(_btn(texts.BTN_NEXT, LibCb(action=action, kind=kind, arg=arg, page=page + 1)))
        rows.append(nav)
    rows.append(_home_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def output_detail_keyboard(cb: LibCb) -> InlineKeyboardMarkup:
    rows = []
    if cb.src in {a.value for a in LIST_ACTIONS}:
        back = LibCb(action=LibAction(cb.src), kind=cb.kind, arg=cb.arg, page=cb.page)
        rows.append([_btn(texts.BTN_LIB_BACK_TO_LIST, back)])
    rows.append(_home_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)
