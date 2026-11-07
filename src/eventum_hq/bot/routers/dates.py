"""Shared Jalali date + time picker (handoff §5.3).

A flow starts it with :func:`start_date_input` and a *purpose*. When the user
has chosen a date and time (and confirmed a past one), the handler registered
for that purpose with :func:`on_date_chosen` runs. Handlers receive aiogram's
data dict (current_user, services, clock, …), so the picker itself knows
nothing about tasks, delegations or reels.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date, datetime, time
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from eventum_hq.bot import texts
from eventum_hq.bot.formatters import format_jalali_date, format_jalali_datetime
from eventum_hq.bot.keyboards.tasks import (
    DateCb,
    DateKind,
    past_confirm_keyboard,
    quick_date_keyboard,
    time_keyboard,
)
from eventum_hq.bot.states import DateInput
from eventum_hq.bot.task_ui import FREE_TEXT, reply
from eventum_hq.core.jalali import (
    InvalidDateInput,
    InvalidTimeInput,
    parse_date_input,
    parse_time_input,
    quick_date,
    tehran_to_utc,
    tehran_today,
)
from eventum_hq.core.timeutil import Clock

router = Router(name="dates")

DateChosen = Callable[[Message | CallbackQuery, FSMContext, datetime, dict[str, Any]], Awaitable[None]]
_HANDLERS: dict[str, DateChosen] = {}

_PURPOSE_KEY = "date_purpose"
_PROMPT_KEY = "date_prompt"


def on_date_chosen(purpose: str) -> Callable[[DateChosen], DateChosen]:
    """Register what happens when a date for ``purpose`` has been chosen."""

    def register(handler: DateChosen) -> DateChosen:
        _HANDLERS[purpose] = handler
        return handler

    return register


async def start_date_input(
    event: Message | CallbackQuery, state: FSMContext, purpose: str, prompt: str, *, new_message: bool = False,
    **flow_data: Any,
) -> None:
    """Switch to the date picker. Keeps existing FSM data (the surrounding flow's answers)."""
    await state.update_data({_PURPOSE_KEY: purpose, _PROMPT_KEY: prompt, **flow_data})
    await state.set_state(DateInput.date)
    if new_message and isinstance(event, CallbackQuery) and isinstance(event.message, Message):
        await event.message.answer(prompt, reply_markup=quick_date_keyboard())
    else:
        await reply(event, prompt, quick_date_keyboard())


@router.callback_query(DateInput.date, DateCb.filter(F.kind == DateKind.QUICK))
async def on_quick_date(query: CallbackQuery, callback_data: DateCb, state: FSMContext, clock: Clock) -> None:
    try:
        day = quick_date(callback_data.value, tehran_today(clock.now()))
    except ValueError:
        await query.answer(texts.STALE_BUTTON, show_alert=True)
        return
    await _ask_time(query, state, day)
    await query.answer()


@router.message(DateInput.date, FREE_TEXT)
async def on_manual_date(message: Message, state: FSMContext, clock: Clock, **data: Any) -> None:
    try:
        parsed = parse_date_input(message.text or "", tehran_today(clock.now()))
    except InvalidDateInput:
        await message.answer(texts.INVALID_DATE)
        return
    if parsed.time is None:
        await _ask_time(message, state, parsed.date)
        return
    await _finish(message, state, parsed.date, parsed.time, clock, data)


async def _ask_time(event: Message | CallbackQuery, state: FSMContext, day: date) -> None:
    await state.update_data(due_date=day.isoformat())
    await state.set_state(DateInput.time)
    await reply(event, texts.DUE_TIME_PROMPT.format(date=format_jalali_date(day)), time_keyboard())


@router.callback_query(DateInput.time, DateCb.filter(F.kind == DateKind.TIME))
async def on_time_button(
    query: CallbackQuery, callback_data: DateCb, state: FSMContext, clock: Clock, **data: Any
) -> None:
    value = callback_data.value
    try:
        at = time(int(value[:2]), int(value[2:]))
    except ValueError:
        await query.answer(texts.STALE_BUTTON, show_alert=True)
        return
    day = date.fromisoformat((await state.get_data())["due_date"])
    await _finish(query, state, day, at, clock, data)
    await query.answer()


@router.message(DateInput.time, FREE_TEXT)
async def on_manual_time(message: Message, state: FSMContext, clock: Clock, **data: Any) -> None:
    try:
        at = parse_time_input(message.text or "")
    except InvalidTimeInput:
        await message.answer(texts.INVALID_TIME)
        return
    day = date.fromisoformat((await state.get_data())["due_date"])
    await _finish(message, state, day, at, clock, data)


async def _finish(
    event: Message | CallbackQuery, state: FSMContext, day: date, at: time, clock: Clock, data: dict[str, Any]
) -> None:
    chosen = tehran_to_utc(day, at)
    if chosen < clock.now():
        await state.update_data(due_at=chosen.isoformat())
        await state.set_state(DateInput.past_confirm)
        await reply(event, texts.DUE_PAST_CONFIRM.format(due=format_jalali_datetime(chosen)),
                    past_confirm_keyboard())
        return
    await _done(event, state, chosen, data)


@router.callback_query(DateInput.past_confirm, DateCb.filter(F.kind == DateKind.PAST_YES))
async def on_past_yes(query: CallbackQuery, state: FSMContext, **data: Any) -> None:
    chosen = datetime.fromisoformat((await state.get_data())["due_at"])
    await _done(query, state, chosen, data)
    await query.answer()


@router.callback_query(DateInput.past_confirm, DateCb.filter(F.kind == DateKind.PAST_NO))
async def on_past_no(query: CallbackQuery, state: FSMContext) -> None:
    prompt = (await state.get_data()).get(_PROMPT_KEY) or texts.DUE_DATE_PROMPT
    await state.set_state(DateInput.date)
    await reply(query, prompt, quick_date_keyboard())
    await query.answer()


async def _done(event: Message | CallbackQuery, state: FSMContext, chosen: datetime, data: dict[str, Any]) -> None:
    purpose = (await state.get_data()).get(_PURPOSE_KEY)
    handler = _HANDLERS.get(purpose or "")
    if handler is None:  # should not happen; leave cleanly
        await state.clear()
        await reply(event, texts.STALE_BUTTON)
        return
    await handler(event, state, chosen, {**data, "state": state})


@router.callback_query(DateCb.filter())
async def on_stale(query: CallbackQuery) -> None:
    await query.answer(texts.STALE_BUTTON, show_alert=True)
