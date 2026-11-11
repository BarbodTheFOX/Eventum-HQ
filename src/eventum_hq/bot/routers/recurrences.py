"""🔁 Recurring tasks (F10, handoff §4.10), under 👥 تیم.

List → ➕ new: title → assignee → every day / chosen weekdays → create time →
due time → approval chain → estimate → confirm. ⛔️ stops one recurrence; tasks
already created stay as they are. The service re-checks CREATE_TASK.
"""

from __future__ import annotations

from datetime import time

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from eventum_hq.bot import texts
from eventum_hq.bot.formatters import (
    esc,
    format_hhmm,
    format_minutes,
    recurrence_list_text,
    recurrence_rule_label,
    user_label,
)
from eventum_hq.bot.keyboards.main_menu import AdminViews, menu_for
from eventum_hq.bot.keyboards.recurrences import (
    CREATE_TIME_CHOICES,
    DUE_TIME_CHOICES,
    RecurAction,
    RecurCb,
    assignee_keyboard,
    chain_keyboard,
    confirm_keyboard,
    estimate_keyboard,
    recurrence_list_keyboard,
    rule_keyboard,
    time_choice_keyboard,
    weekdays_keyboard,
)
from eventum_hq.bot.states import RecurrenceFlow
from eventum_hq.bot.task_ui import FREE_TEXT, reply
from eventum_hq.core.errors import NotFound, PermissionDenied, ValidationFailed
from eventum_hq.core.jalali import InvalidTimeInput, parse_time_input
from eventum_hq.models import ApprovalChain, Capability, RecurrenceRule, User
from eventum_hq.services.permissions import has_capability
from eventum_hq.services.recurrences import NewRecurrence, RecurrenceService
from eventum_hq.services.tasks import TITLE_MAX, TaskService

router = Router(name="recurrences")


def _hhmm(value: str) -> time:
    return time(int(value[:2]), int(value[2:]))


async def _show_list(event: Message | CallbackQuery, user: User, recurrences: RecurrenceService) -> None:
    rows = await recurrences.list_active(user)
    await reply(event, recurrence_list_text(rows), recurrence_list_keyboard(rows))


@router.callback_query(RecurCb.filter(F.action == RecurAction.LIST))
async def on_list(query: CallbackQuery, state: FSMContext, current_user: User,
                  recurrences: RecurrenceService) -> None:
    await state.clear()
    try:
        await _show_list(query, current_user, recurrences)
    except PermissionDenied:
        await query.answer(texts.PERMISSION_DENIED, show_alert=True)
        return
    await query.answer()


@router.callback_query(RecurCb.filter(F.action == RecurAction.STOP))
async def on_stop(query: CallbackQuery, callback_data: RecurCb, current_user: User,
                  recurrences: RecurrenceService) -> None:
    try:
        stopped = await recurrences.deactivate(current_user, callback_data.arg)
        rows = await recurrences.list_active(current_user)
    except (PermissionDenied, NotFound):
        await query.answer(texts.PERMISSION_DENIED, show_alert=True)
        return
    await reply(query, texts.RECURRENCE_STOPPED.format(title=esc(stopped.title)) + "\n\n" + recurrence_list_text(rows),
                recurrence_list_keyboard(rows))
    await query.answer()


@router.callback_query(RecurCb.filter(F.action == RecurAction.NEW))
async def on_new(query: CallbackQuery, state: FSMContext, current_user: User) -> None:
    if not has_capability(current_user, Capability.CREATE_TASK):
        await query.answer(texts.PERMISSION_DENIED, show_alert=True)
        return
    await state.clear()
    await state.set_state(RecurrenceFlow.title)
    await reply(query, texts.NEW_RECURRENCE_TITLE)
    await query.answer()


@router.message(RecurrenceFlow.title, FREE_TEXT)
async def on_title(message: Message, state: FSMContext, tasks: TaskService) -> None:
    title = (message.text or "").strip()
    if not title or len(title) > TITLE_MAX:
        await message.answer(texts.VALIDATION_MESSAGES.get("title_too_long" if title else "title_empty",
                                                           texts.GENERIC_ERROR))
        return
    await state.update_data(title=title)
    await state.set_state(RecurrenceFlow.assignee)
    await message.answer(texts.NEW_RECURRENCE_ASSIGNEE, reply_markup=assignee_keyboard(await tasks.assignable_users()))


@router.callback_query(RecurrenceFlow.assignee, RecurCb.filter(F.action == RecurAction.ASSIGNEE))
async def on_assignee(query: CallbackQuery, callback_data: RecurCb, state: FSMContext) -> None:
    await state.update_data(assignee_id=callback_data.arg)
    await state.set_state(RecurrenceFlow.rule)
    await reply(query, texts.NEW_RECURRENCE_RULE, rule_keyboard())
    await query.answer()


@router.callback_query(RecurrenceFlow.rule, RecurCb.filter(F.action == RecurAction.RULE))
async def on_rule(query: CallbackQuery, callback_data: RecurCb, state: FSMContext) -> None:
    rule = RecurrenceRule(callback_data.value)
    await state.update_data(rule=rule.value, weekdays=[])
    if rule == RecurrenceRule.WEEKDAYS:
        await state.set_state(RecurrenceFlow.weekdays)
        await reply(query, texts.NEW_RECURRENCE_WEEKDAYS, weekdays_keyboard(set()))
    else:
        await _ask_create_time(query, state)
    await query.answer()


@router.callback_query(RecurrenceFlow.weekdays, RecurCb.filter(F.action == RecurAction.DAY))
async def on_day(query: CallbackQuery, callback_data: RecurCb, state: FSMContext) -> None:
    selected = set((await state.get_data()).get("weekdays") or [])
    selected ^= {callback_data.arg}
    await state.update_data(weekdays=sorted(selected))
    await reply(query, texts.NEW_RECURRENCE_WEEKDAYS, weekdays_keyboard(selected))
    await query.answer()


@router.callback_query(RecurrenceFlow.weekdays, RecurCb.filter(F.action == RecurAction.DAYS_DONE))
async def on_days_done(query: CallbackQuery, state: FSMContext) -> None:
    if not (await state.get_data()).get("weekdays"):
        await query.answer(texts.WEEKDAYS_REQUIRED, show_alert=True)
        return
    await _ask_create_time(query, state)
    await query.answer()


async def _ask_create_time(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.set_state(RecurrenceFlow.create_time)
    await reply(event, texts.NEW_RECURRENCE_CREATE_TIME,
                time_choice_keyboard(RecurAction.CREATE_TIME, CREATE_TIME_CHOICES))


@router.callback_query(RecurrenceFlow.create_time, RecurCb.filter(F.action == RecurAction.CREATE_TIME))
async def on_create_time_button(query: CallbackQuery, callback_data: RecurCb, state: FSMContext) -> None:
    await _set_create_time(query, state, _hhmm(callback_data.value))
    await query.answer()


@router.message(RecurrenceFlow.create_time, FREE_TEXT)
async def on_create_time_text(message: Message, state: FSMContext) -> None:
    try:
        at = parse_time_input(message.text or "")
    except InvalidTimeInput:
        await message.answer(texts.INVALID_TIME)
        return
    await _set_create_time(message, state, at)


async def _set_create_time(event: Message | CallbackQuery, state: FSMContext, at: time) -> None:
    await state.update_data(create_time=at.strftime("%H%M"))
    await state.set_state(RecurrenceFlow.due_time)
    await reply(event, texts.NEW_RECURRENCE_DUE_TIME, time_choice_keyboard(RecurAction.DUE_TIME, DUE_TIME_CHOICES))


@router.callback_query(RecurrenceFlow.due_time, RecurCb.filter(F.action == RecurAction.DUE_TIME))
async def on_due_time_button(query: CallbackQuery, callback_data: RecurCb, state: FSMContext) -> None:
    await _set_due_time(query, state, _hhmm(callback_data.value))
    await query.answer()


@router.message(RecurrenceFlow.due_time, FREE_TEXT)
async def on_due_time_text(message: Message, state: FSMContext) -> None:
    try:
        at = parse_time_input(message.text or "")
    except InvalidTimeInput:
        await message.answer(texts.INVALID_TIME)
        return
    await _set_due_time(message, state, at)


async def _set_due_time(event: Message | CallbackQuery, state: FSMContext, at: time) -> None:
    create = _hhmm((await state.get_data())["create_time"])
    if at <= create:
        await reply(event, texts.VALIDATION_MESSAGES["due_before_create"] + "\n\n" + texts.NEW_RECURRENCE_DUE_TIME,
                    time_choice_keyboard(RecurAction.DUE_TIME, DUE_TIME_CHOICES))
        return
    await state.update_data(due_time=at.strftime("%H%M"))
    await state.set_state(RecurrenceFlow.chain)
    await reply(event, texts.NEW_TASK_CHAIN, chain_keyboard())


@router.callback_query(RecurrenceFlow.chain, RecurCb.filter(F.action == RecurAction.CHAIN))
async def on_chain(query: CallbackQuery, callback_data: RecurCb, state: FSMContext) -> None:
    await state.update_data(chain=ApprovalChain(callback_data.value).value)
    await state.set_state(RecurrenceFlow.estimate)
    await reply(query, texts.NEW_TASK_ESTIMATE, estimate_keyboard())
    await query.answer()


@router.callback_query(RecurrenceFlow.estimate, RecurCb.filter(F.action == RecurAction.ESTIMATE))
async def on_estimate(query: CallbackQuery, callback_data: RecurCb, state: FSMContext,
                      tasks: TaskService) -> None:
    await state.update_data(estimated_minutes=callback_data.arg or None)
    await state.set_state(RecurrenceFlow.confirm)
    data = await state.get_data()
    users = {u.id: u for u in await tasks.assignable_users()}
    summary = texts.NEW_RECURRENCE_SUMMARY.format(
        title=esc(data["title"]),
        assignee=user_label(users.get(int(data["assignee_id"]))),
        rule=recurrence_rule_label(data["rule"], list(data.get("weekdays") or [])),
        create=format_hhmm(_hhmm(data["create_time"])),
        due=format_hhmm(_hhmm(data["due_time"])),
        chain=texts.CHAIN_LABELS[ApprovalChain(data["chain"])],
        estimate=format_minutes(data.get("estimated_minutes")),
    )
    await reply(query, summary, confirm_keyboard())
    await query.answer()


@router.callback_query(RecurrenceFlow.confirm, RecurCb.filter(F.action == RecurAction.CREATE))
async def on_create(query: CallbackQuery, state: FSMContext, current_user: User,
                    recurrences: RecurrenceService) -> None:
    data = await state.get_data()
    try:
        created = await recurrences.create(current_user, NewRecurrence(
            title=data["title"],
            assignee_id=int(data["assignee_id"]),
            rule=RecurrenceRule(data["rule"]),
            weekdays=list(data.get("weekdays") or []),
            create_time=_hhmm(data["create_time"]),
            due_time=_hhmm(data["due_time"]),
            approval_chain=ApprovalChain(data["chain"]),
            estimated_minutes=data.get("estimated_minutes"),
        ))
    except PermissionDenied:
        await state.clear()
        await query.answer(texts.PERMISSION_DENIED, show_alert=True)
        return
    except ValidationFailed as exc:
        await query.answer(texts.VALIDATION_MESSAGES.get(exc.code, texts.GENERIC_ERROR), show_alert=True)
        return
    await state.clear()
    rows = await recurrences.list_active(current_user)
    await reply(query, texts.RECURRENCE_CREATED.format(title=esc(created.title)) + "\n\n"
                + recurrence_list_text(rows), recurrence_list_keyboard(rows))
    await query.answer()


@router.callback_query(RecurCb.filter(F.action == RecurAction.ABORT))
async def on_abort(query: CallbackQuery, state: FSMContext, current_user: User, admin_views: AdminViews) -> None:
    await state.clear()
    await reply(query, texts.FLOW_ABORTED)
    await query.answer()
    if isinstance(query.message, Message):
        await query.message.answer(texts.MENU_SHOWN, reply_markup=menu_for(current_user, admin_views))


@router.callback_query(RecurCb.filter())
async def on_stale(query: CallbackQuery) -> None:
    await query.answer(texts.STALE_BUTTON, show_alert=True)
