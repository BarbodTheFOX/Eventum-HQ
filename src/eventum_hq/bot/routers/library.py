"""📚 Library of approved outputs (F9, handoff §4.9).

Opening the library puts the user in ``LibraryFlow.search``: any free text is
then a search (title, series, code, assignee name). Commands and menu buttons
still work and leave the library. Lists are paged (8 per page); pressing an
item sends its details and copies its files from the archive channel.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from eventum_hq.bot import texts
from eventum_hq.bot.formatters import esc, library_list_text, output_detail_text
from eventum_hq.bot.keyboards.library import (
    LibAction,
    LibCb,
    library_home_keyboard,
    library_list_keyboard,
    library_series_keyboard,
    output_detail_keyboard,
)
from eventum_hq.bot.keyboards.main_menu import AdminViews, menu_for
from eventum_hq.bot.keyboards.tasks import PAGE_SIZE, page_slice
from eventum_hq.bot.states import LibraryFlow
from eventum_hq.bot.task_ui import FREE_TEXT, reply
from eventum_hq.core.errors import NotFound, PermissionDenied
from eventum_hq.integrations.telegram_archive import TelegramArchive
from eventum_hq.models import User
from eventum_hq.services.outputs import QUERY_MAX, LibraryKind, LibraryService, OutputRow
from eventum_hq.services.permissions import MenuItem, can_use_menu_item

router = Router(name="library")
log = logging.getLogger(__name__)

QUERY_KEY = "lib_query"


@router.message(F.text == texts.MENU_LABELS[MenuItem.LIBRARY])
async def menu_library(message: Message, state: FSMContext, current_user: User, admin_views: AdminViews) -> None:
    await state.clear()
    if not can_use_menu_item(current_user, MenuItem.LIBRARY):
        await message.answer(texts.PERMISSION_DENIED, reply_markup=menu_for(current_user, admin_views))
        return
    await state.set_state(LibraryFlow.search)
    await message.answer(texts.LIBRARY_HOME, reply_markup=library_home_keyboard())


@router.message(LibraryFlow.search, FREE_TEXT)
async def on_search_text(message: Message, state: FSMContext, current_user: User, library: LibraryService) -> None:
    query = (message.text or "").strip()[:QUERY_MAX]
    await state.update_data({QUERY_KEY: query})
    try:
        rows = await library.search(current_user, query)
    except PermissionDenied:
        await message.answer(texts.PERMISSION_DENIED)
        return
    text, markup = _list_view(texts.LIB_SEARCH_TITLE.format(query=esc(query)), rows,
                              action=LibAction.QUERY, kind="", arg=0, page=0,
                              empty_text=texts.LIB_EMPTY + texts.LIB_SEARCH_EMPTY_HINT)
    await message.answer(text, reply_markup=markup)


@router.callback_query(LibCb.filter())
async def on_library(query: CallbackQuery, callback_data: LibCb, state: FSMContext, current_user: User,
                     library: LibraryService, archive: TelegramArchive) -> None:
    # Server-side check: everyone active may use the library (§3.2), nobody else.
    if not can_use_menu_item(current_user, MenuItem.LIBRARY):
        await query.answer(texts.PERMISSION_DENIED, show_alert=True)
        return
    action = callback_data.action
    try:
        if action == LibAction.HOME:
            await state.clear()
            await state.set_state(LibraryFlow.search)
            await reply(query, texts.LIBRARY_HOME, library_home_keyboard())
        elif action == LibAction.PICK_SERIES:
            series = await library.series_with_outputs(current_user)
            if not series:
                await query.answer(texts.LIB_NO_SERIES, show_alert=True)
                return
            await reply(query, texts.LIB_PICK_SERIES, library_series_keyboard(series))
        elif action == LibAction.OPEN:
            await _open(query, callback_data, current_user, library, archive)
        else:
            shown = await _show_list(query, callback_data, state, current_user, library)
            if not shown:
                return
    except PermissionDenied:
        await query.answer(texts.PERMISSION_DENIED, show_alert=True)
        return
    except NotFound:
        await query.answer(texts.LIB_NOT_FOUND, show_alert=True)
        return
    await query.answer()


async def _show_list(query: CallbackQuery, cb: LibCb, state: FSMContext, user: User,
                     library: LibraryService) -> bool:
    action, kind, arg = cb.action, cb.kind, cb.arg
    empty_text = texts.LIB_EMPTY
    if action == LibAction.RECENT:
        rows = await library.recent(user)
        title, empty_text = texts.LIB_RECENT_TITLE, texts.LIB_EMPTY_LIBRARY
    elif action == LibAction.KIND:
        try:
            library_kind = LibraryKind(kind)
        except ValueError:
            await query.answer(texts.STALE_BUTTON, show_alert=True)
            return False
        rows = await library.by_kind(user, library_kind)
        title = texts.LIB_KIND_TITLES[library_kind.value]
    elif action == LibAction.SERIES:
        series = {s.id: s for s in await library.series_with_outputs(user)}
        if arg not in series:
            await query.answer(texts.LIB_NOT_FOUND, show_alert=True)
            return False
        rows = await library.by_series(user, arg)
        title = texts.LIB_SERIES_TITLE.format(name=esc(series[arg].name))
    else:  # QUERY: the text is in FSM data, not in the button
        text = (await state.get_data()).get(QUERY_KEY)
        if not text:
            await query.answer(texts.LIB_SEARCH_EXPIRED, show_alert=True)
            return False
        rows = await library.search(user, text)
        title = texts.LIB_SEARCH_TITLE.format(query=esc(text))
    body, markup = _list_view(title, rows, action=action, kind=kind, arg=arg, page=cb.page, empty_text=empty_text)
    await reply(query, body, markup)
    return True


def _list_view(title: str, rows: list[OutputRow], *, action: LibAction, kind: str, arg: int, page: int,
               empty_text: str) -> tuple[str, InlineKeyboardMarkup]:
    page_rows, page, pages = page_slice(rows, page)
    text = library_list_text(title, rows, page_rows, page * PAGE_SIZE + 1, empty_text=empty_text)
    markup = library_list_keyboard(page_rows, action=action, kind=kind, arg=arg, page=page, pages=pages)
    return text, markup


async def _open(query: CallbackQuery, cb: LibCb, user: User, library: LibraryService,
                archive: TelegramArchive) -> None:
    detail = await library.detail(user, cb.item)
    if not isinstance(query.message, Message):
        return
    chat_id = query.message.chat.id
    await query.message.answer(output_detail_text(detail), reply_markup=output_detail_keyboard(cb))
    failed = False
    for attachment in detail.attachments:
        try:
            await archive.send_to(chat_id, attachment, caption=detail.task.code)
        except TelegramAPIError as exc:
            log.warning("could not send a library file: %s", exc)
            failed = True
    if failed:
        await query.message.answer(texts.LIB_FILE_FAILED)
