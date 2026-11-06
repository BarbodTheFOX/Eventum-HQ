"""Main menu, /menu, /help, /my, /cancel and the (still empty) menu sections."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from eventum_hq.bot import texts
from eventum_hq.bot.keyboards.main_menu import LABEL_TO_ITEM, main_menu
from eventum_hq.models import User
from eventum_hq.services.permissions import MenuItem, can_use_menu_item

router = Router(name="menu")


@router.message(Command("menu"))
async def cmd_menu(message: Message, current_user: User) -> None:
    await message.answer(texts.MENU_SHOWN, reply_markup=main_menu(current_user))


@router.message(Command("help"))
async def cmd_help(message: Message, current_user: User) -> None:
    await message.answer(texts.HELP, reply_markup=main_menu(current_user))


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, current_user: User) -> None:
    had_state = await state.get_state() is not None
    await state.clear()
    text = texts.CANCELLED if had_state else texts.NOTHING_TO_CANCEL
    await message.answer(text, reply_markup=main_menu(current_user))


@router.message(Command("my"))
async def cmd_my(message: Message, current_user: User) -> None:
    await _open_section(message, current_user, MenuItem.MY_TASKS)


@router.message(F.text.in_(set(LABEL_TO_ITEM)))
async def on_menu_button(message: Message, current_user: User) -> None:
    item = LABEL_TO_ITEM[message.text or ""]
    await _open_section(message, current_user, item)


async def _open_section(message: Message, user: User, item: MenuItem) -> None:
    # Re-check on the server: the user may have typed the label by hand.
    if not can_use_menu_item(user, item):
        await message.answer(texts.PERMISSION_DENIED, reply_markup=main_menu(user))
        return
    if item == MenuItem.HELP:
        await message.answer(texts.HELP, reply_markup=main_menu(user))
        return
    await message.answer(
        texts.COMING_SOON.format(label=texts.MENU_LABELS[item]), reply_markup=main_menu(user)
    )


@router.message()
async def fallback(message: Message, current_user: User) -> None:
    await message.answer(texts.UNKNOWN_INPUT, reply_markup=main_menu(current_user))
