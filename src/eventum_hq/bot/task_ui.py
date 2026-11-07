"""Helpers shared by the task routers (sending/editing cards, replying to either event type)."""

from __future__ import annotations

import logging

from aiogram import F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from eventum_hq.bot import texts
from eventum_hq.bot.formatters import task_card
from eventum_hq.bot.keyboards.tasks import task_card_keyboard
from eventum_hq.core.timeutil import Clock
from eventum_hq.models import User
from eventum_hq.services.tasks import TaskService

log = logging.getLogger(__name__)

MENU_LABELS = set(texts.MENU_LABELS.values())

# A plain text message that is neither a command nor a main-menu button.
FREE_TEXT = F.text & ~F.text.startswith("/") & ~F.text.in_(MENU_LABELS)


async def reply(event: Message | CallbackQuery, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    """Edit the message under a pressed button, or answer a typed message."""
    if isinstance(event, CallbackQuery):
        if isinstance(event.message, Message):
            try:
                await event.message.edit_text(text, reply_markup=markup)
                return
            except TelegramBadRequest as exc:
                if "not modified" in str(exc):
                    return
                log.debug("edit failed, sending new message: %s", exc)
            await event.message.answer(text, reply_markup=markup)
        return
    await event.answer(text, reply_markup=markup)


async def send_card(
    message: Message, tasks: TaskService, viewer: User, task_id: int, clock: Clock, prefix: str = ""
) -> None:
    view = await tasks.get_view(viewer, task_id=task_id)
    await message.answer(prefix + task_card(view, clock.now()), reply_markup=task_card_keyboard(view))


async def edit_card(
    query: CallbackQuery,
    tasks: TaskService,
    viewer: User,
    task_id: int,
    clock: Clock,
    *,
    suffix: str = "",
    markup: InlineKeyboardMarkup | None = None,
) -> None:
    view = await tasks.get_view(viewer, task_id=task_id)
    await reply(query, task_card(view, clock.now()) + suffix, markup or task_card_keyboard(view))
