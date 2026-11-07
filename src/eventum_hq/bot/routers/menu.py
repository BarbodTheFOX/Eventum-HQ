"""Main menu, /menu, /help, /my, /cancel, admin view and the (still empty) sections."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from eventum_hq.bot import texts
from eventum_hq.bot.keyboards.main_menu import LABEL_TO_ITEM, AdminViews, main_menu, menu_for
from eventum_hq.models import User
from eventum_hq.services.permissions import MenuItem, can_use_menu_item

router = Router(name="menu")


@router.message(Command("menu"))
async def cmd_menu(message: Message, current_user: User, admin_views: AdminViews) -> None:
    await message.answer(texts.MENU_SHOWN, reply_markup=menu_for(current_user, admin_views))


@router.message(Command("help"))
async def cmd_help(message: Message, current_user: User, admin_views: AdminViews) -> None:
    await message.answer(texts.HELP, reply_markup=menu_for(current_user, admin_views))


@router.message(Command("cancel"))
async def cmd_cancel(
    message: Message, state: FSMContext, current_user: User, admin_views: AdminViews
) -> None:
    had_state = await state.get_state() is not None
    await state.clear()
    text = texts.CANCELLED if had_state else texts.NOTHING_TO_CANCEL
    await message.answer(text, reply_markup=menu_for(current_user, admin_views))


@router.message(Command("my"))
async def cmd_my(message: Message, current_user: User, admin_views: AdminViews) -> None:
    await _open_section(message, current_user, admin_views, MenuItem.MY_TASKS)


@router.message(F.text.in_(set(LABEL_TO_ITEM)))
async def on_menu_button(message: Message, current_user: User, admin_views: AdminViews) -> None:
    item = LABEL_TO_ITEM[message.text or ""]
    await _open_section(message, current_user, admin_views, item)


async def _open_section(
    message: Message, user: User, admin_views: AdminViews, item: MenuItem
) -> None:
    # Re-check on the server: the user may have typed the label by hand.
    if not can_use_menu_item(user, item):
        await message.answer(texts.PERMISSION_DENIED, reply_markup=menu_for(user, admin_views))
        return
    if item in (MenuItem.ADMIN_VIEW_ON, MenuItem.ADMIN_VIEW_OFF):
        on = item == MenuItem.ADMIN_VIEW_ON
        admin_views.set(user.telegram_id, on)
        text = texts.ADMIN_VIEW_ENABLED if on else texts.ADMIN_VIEW_DISABLED
        await message.answer(text, reply_markup=main_menu(user, admin_view=on))
        return
    if item == MenuItem.HELP:
        await message.answer(texts.HELP, reply_markup=menu_for(user, admin_views))
        return
    await message.answer(
        texts.COMING_SOON.format(label=texts.MENU_LABELS[item]),
        reply_markup=menu_for(user, admin_views),
    )


@router.message()
async def fallback(message: Message, current_user: User, admin_views: AdminViews) -> None:
    await message.answer(texts.UNKNOWN_INPUT, reply_markup=menu_for(current_user, admin_views))
