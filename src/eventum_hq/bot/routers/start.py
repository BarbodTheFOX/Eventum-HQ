"""/start — known users see the menu; unknown users trigger an access request."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove

from eventum_hq.bot import texts
from eventum_hq.bot.formatters import esc
from eventum_hq.bot.keyboards.main_menu import main_menu
from eventum_hq.models import User
from eventum_hq.services.users import StartResult, UserService

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(
    message: Message, state: FSMContext, users: UserService, current_user: User | None
) -> None:
    tg = message.from_user
    if tg is None:
        return
    await state.clear()
    outcome = await users.start(
        telegram_id=tg.id, full_name=tg.full_name, username=tg.username
    )

    if outcome.result == StartResult.KNOWN:
        user = outcome.user
        text = (
            texts.WELCOME_KNOWN.format(name=esc(user.full_name))
            if user.full_name
            else texts.WELCOME_KNOWN_NO_NAME
        )
        await message.answer(text, reply_markup=main_menu(user))
    elif outcome.result == StartResult.REQUEST_SENT:
        await message.answer(texts.ACCESS_REQUEST_SENT, reply_markup=ReplyKeyboardRemove())
    else:
        await message.answer(texts.ACCESS_REQUEST_ALREADY_SENT, reply_markup=ReplyKeyboardRemove())
