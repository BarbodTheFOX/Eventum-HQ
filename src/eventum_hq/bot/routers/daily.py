"""📝 Daily operations report (M7): evening notes in, a rich-message report out.

Opening the section puts the user in ``DailyReportFlow.notes``: every free text
is stored as one note (in the DB, so nothing is lost on restart). Commands and
menu buttons still work and leave the section. «👁 پیش‌نمایش» sends the report
with buttons; «✅ نهایی‌کردن» sends a clean copy (to forward) and records it.
"""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InputRichMessage, Message

from eventum_hq.bot import texts
from eventum_hq.bot.daily_render import render_html, render_markdown
from eventum_hq.bot.formatters import esc, fa_digits, format_jalali_date, user_label
from eventum_hq.bot.keyboards.daily import (
    DailyAction,
    DailyCb,
    daily_clear_keyboard,
    daily_home_keyboard,
    daily_preview_keyboard,
    daily_saved_keyboard,
)
from eventum_hq.bot.keyboards.main_menu import AdminViews, menu_for
from eventum_hq.bot.outbox import split_text
from eventum_hq.bot.states import DailyReportFlow
from eventum_hq.bot.task_ui import FREE_TEXT
from eventum_hq.core.errors import PermissionDenied, ValidationFailed
from eventum_hq.core.timeutil import to_tehran
from eventum_hq.models import User
from eventum_hq.services.daily_report import DailyReport, DailyReportService
from eventum_hq.services.permissions import MenuItem, can_use_menu_item

router = Router(name="daily")
log = logging.getLogger(__name__)


async def _home_text(daily: DailyReportService, user: User) -> str:
    notes = await daily.notes(user)
    return texts.DAILY_HOME.format(date=format_jalali_date(daily.today()), count=fa_digits(len(notes)))


@router.message(F.text == texts.MENU_LABELS[MenuItem.DAILY_REPORT])
async def menu_daily(message: Message, state: FSMContext, current_user: User, daily: DailyReportService,
                     admin_views: AdminViews) -> None:
    await state.clear()
    if not can_use_menu_item(current_user, MenuItem.DAILY_REPORT):
        await message.answer(texts.PERMISSION_DENIED, reply_markup=menu_for(current_user, admin_views))
        return
    try:
        text = await _home_text(daily, current_user)
    except PermissionDenied:
        await message.answer(texts.PERMISSION_DENIED, reply_markup=menu_for(current_user, admin_views))
        return
    await state.set_state(DailyReportFlow.notes)
    await message.answer(text, reply_markup=daily_home_keyboard())


@router.message(DailyReportFlow.notes, FREE_TEXT)
async def on_note(message: Message, state: FSMContext, current_user: User, daily: DailyReportService,
                  admin_views: AdminViews) -> None:
    try:
        count = await daily.add_note(current_user, message.text or "")
    except PermissionDenied:
        await state.clear()
        await message.answer(texts.PERMISSION_DENIED, reply_markup=menu_for(current_user, admin_views))
        return
    except ValidationFailed as exc:
        await message.answer(texts.VALIDATION_MESSAGES.get(exc.code, texts.GENERIC_ERROR))
        return
    await message.answer(texts.DAILY_NOTE_SAVED.format(count=fa_digits(count)), reply_markup=daily_saved_keyboard())


async def send_report(bot: Bot, chat_id: int, report: DailyReport, markup: InlineKeyboardMarkup | None) -> None:
    """Send as a rich message; if Telegram refuses it, send the same report as ordinary HTML text."""
    try:
        await bot.send_rich_message(
            chat_id=chat_id,
            rich_message=InputRichMessage(markdown=render_markdown(report), is_rtl=True),
            reply_markup=markup,
        )
        return
    except TelegramAPIError as exc:
        log.warning("rich message refused, falling back to HTML: %s", exc)
    parts = split_text(render_html(report))
    for i, part in enumerate(parts):
        await bot.send_message(chat_id=chat_id, text=part, reply_markup=markup if i == len(parts) - 1 else None)
    await bot.send_message(chat_id=chat_id, text=texts.DAILY_RICH_FALLBACK)


@router.callback_query(DailyCb.filter())
async def on_daily(query: CallbackQuery, callback_data: DailyCb, state: FSMContext, current_user: User,
                   daily: DailyReportService, bot: Bot) -> None:
    chat_id = query.from_user.id
    action = callback_data.action
    try:
        if action == DailyAction.PREVIEW:
            report = await daily.build(current_user)
            if report.empty:
                await query.answer(texts.DAILY_NOTHING_TO_REPORT, show_alert=True)
                return
            await query.answer()
            await send_report(bot, chat_id, report, daily_preview_keyboard())
            await bot.send_message(chat_id=chat_id, text=texts.DAILY_PREVIEW_HINT)
        elif action == DailyAction.FINAL:
            report = await daily.build(current_user)
            if report.empty:
                await query.answer(texts.DAILY_NOTHING_TO_REPORT, show_alert=True)
                return
            await query.answer()
            await send_report(bot, chat_id, report, None)
            await daily.mark_sent(current_user, report)
            await state.clear()
            await bot.send_message(chat_id=chat_id, text=texts.DAILY_FINAL_DONE)
        elif action == DailyAction.LIST:
            notes = await daily.notes(current_user)
            await query.answer()
            if not notes:
                await bot.send_message(chat_id=chat_id, text=texts.DAILY_NOTES_EMPTY)
                return
            authors = await daily.authors(current_user, notes)
            text = texts.DAILY_NOTES_TITLE.format(date=format_jalali_date(daily.today()))
            for i, note in enumerate(notes, start=1):
                text += texts.DAILY_NOTE_LINE.format(
                    n=fa_digits(i),
                    author=user_label(authors.get(note.author_id)),
                    time=fa_digits(to_tehran(note.created_at).strftime("%H:%M")),
                    text=esc(note.text))
            for part in split_text(text):
                await bot.send_message(chat_id=chat_id, text=part)
        elif action == DailyAction.CLEAR_ASK:
            mine = [n for n in await daily.notes(current_user) if n.author_id == current_user.id]
            await query.answer()
            if not mine:
                await bot.send_message(chat_id=chat_id, text=texts.DAILY_NOTHING_TO_CLEAR)
                return
            await bot.send_message(chat_id=chat_id, text=texts.DAILY_CLEAR_CONFIRM.format(count=fa_digits(len(mine))),
                                   reply_markup=daily_clear_keyboard())
        elif action == DailyAction.CLEAR_YES:
            removed = await daily.clear_my_notes(current_user)
            await query.answer()
            await bot.send_message(chat_id=chat_id, text=texts.DAILY_CLEARED.format(count=fa_digits(removed))
                                   if removed else texts.DAILY_NOTHING_TO_CLEAR)
        elif action == DailyAction.ADD:
            await state.set_state(DailyReportFlow.notes)
            await query.answer()
            await bot.send_message(chat_id=chat_id, text=await _home_text(daily, current_user),
                                   reply_markup=daily_home_keyboard())
    except PermissionDenied:
        await state.clear()
        await query.answer(texts.PERMISSION_DENIED, show_alert=True)
