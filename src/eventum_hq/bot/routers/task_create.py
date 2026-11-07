"""➕ New task flow (handoff §4.6, §5.3).

title → description (optional: text/voice/photo/video/file) → assignee →
deadline (quick buttons or Jalali text, then time) → estimated time (optional,
F17) → series → approval chain → confirm. /cancel works at every step; flows expire after 30 minutes idle.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from eventum_hq.bot import texts
from eventum_hq.bot.attachments import extract_attachment
from eventum_hq.bot.formatters import (
    esc,
    format_jalali_datetime,
    format_minutes,
    user_label,
)
from eventum_hq.bot.keyboards.main_menu import AdminViews, menu_for
from eventum_hq.bot.keyboards.tasks import (
    NewTaskCb,
    NewTaskStep,
    new_task_assignee_keyboard,
    new_task_chain_keyboard,
    new_task_confirm_keyboard,
    new_task_estimate_keyboard,
    new_task_series_keyboard,
    skip_description_keyboard,
)
from eventum_hq.bot.routers.dates import on_date_chosen, start_date_input
from eventum_hq.bot.states import PURPOSE_DUE, PURPOSE_NEW, NewTaskFlow
from eventum_hq.bot.task_ui import FREE_TEXT, reply, send_card
from eventum_hq.core.errors import (
    InvalidTransition,
    NotFound,
    PermissionDenied,
    ValidationFailed,
)
from eventum_hq.core.jalali import (
    InvalidEstimateInput,
    parse_estimate_input,
)
from eventum_hq.core.timeutil import Clock
from eventum_hq.models import ApprovalChain, Capability, User
from eventum_hq.services.permissions import has_capability
from eventum_hq.services.tasks import DESCRIPTION_MAX, TITLE_MAX, NewTask, TaskService

router = Router(name="task_create")


# ---- entry -------------------------------------------------------------------


async def start_new_task(message: Message, state: FSMContext, user: User, admin_views: AdminViews) -> None:
    if not has_capability(user, Capability.CREATE_TASK):
        await message.answer(texts.PERMISSION_DENIED, reply_markup=menu_for(user, admin_views))
        return
    await state.clear()
    await state.set_state(NewTaskFlow.title)
    await message.answer(texts.NEW_TASK_TITLE)


async def start_due_edit(query: CallbackQuery, state: FSMContext, task_id: int, code: str) -> None:
    await state.clear()
    await start_date_input(query, state, PURPOSE_DUE, texts.EDIT_DUE_PROMPT.format(code=esc(code)),
                           new_message=True, due_task_id=task_id)


# ---- title / description -------------------------------------------------------


@router.message(NewTaskFlow.title, FREE_TEXT)
async def on_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if not title:
        await message.answer(texts.VALIDATION_MESSAGES["title_empty"])
        return
    if len(title) > TITLE_MAX:
        await message.answer(texts.VALIDATION_MESSAGES["title_too_long"])
        return
    await state.update_data(title=title)
    await state.set_state(NewTaskFlow.description)
    await message.answer(texts.NEW_TASK_DESCRIPTION, reply_markup=skip_description_keyboard())


@router.message(NewTaskFlow.title, ~F.text)
async def on_title_not_text(message: Message) -> None:
    await message.answer(texts.SEND_TITLE_AS_TEXT)


@router.message(NewTaskFlow.description, FREE_TEXT)
async def on_description_text(message: Message, state: FSMContext, tasks: TaskService) -> None:
    text = (message.text or "").strip()
    if len(text) > DESCRIPTION_MAX:
        await message.answer(texts.VALIDATION_MESSAGES["description_too_long"])
        return
    await state.update_data(description=text, attachments=[])
    await _ask_assignee(message, state, tasks)


@router.message(NewTaskFlow.description, ~F.text)
async def on_description_media(message: Message, state: FSMContext, tasks: TaskService) -> None:
    attachment = extract_attachment(message)
    if attachment is None:
        await message.answer(texts.UNSUPPORTED_BRIEF)
        return
    caption = (message.caption or "").strip()[:DESCRIPTION_MAX]
    await state.update_data(description=caption or None, attachments=[attachment])
    await _ask_assignee(message, state, tasks)


@router.callback_query(NewTaskFlow.description, NewTaskCb.filter(F.step == NewTaskStep.SKIP_DESCRIPTION))
async def on_skip_description(query: CallbackQuery, state: FSMContext, tasks: TaskService) -> None:
    await state.update_data(description=None, attachments=[])
    await _ask_assignee(query, state, tasks)
    await query.answer()


async def _ask_assignee(event: Message | CallbackQuery, state: FSMContext, tasks: TaskService) -> None:
    await state.set_state(NewTaskFlow.assignee)
    users = await tasks.assignable_users()
    await reply(event, texts.NEW_TASK_ASSIGNEE, new_task_assignee_keyboard(users))


@router.callback_query(NewTaskFlow.assignee, NewTaskCb.filter(F.step == NewTaskStep.ASSIGNEE))
async def on_assignee(query: CallbackQuery, callback_data: NewTaskCb, state: FSMContext, tasks: TaskService) -> None:
    users = {u.id: u for u in await tasks.assignable_users()}
    try:
        assignee_id = int(callback_data.value)
    except ValueError:
        assignee_id = -1
    if assignee_id not in users:
        await query.answer(texts.VALIDATION_MESSAGES["assignee_inactive"], show_alert=True)
        return
    await state.update_data(assignee_id=assignee_id)
    await start_date_input(query, state, PURPOSE_NEW, texts.DUE_DATE_PROMPT)
    await query.answer()


# ---- deadline (shared picker in routers/dates.py) ---------------------------------


@on_date_chosen(PURPOSE_NEW)
async def _new_task_due_chosen(event: Message | CallbackQuery, state: FSMContext, due: datetime,
                               data: dict[str, Any]) -> None:
    await state.update_data(due_at=due.isoformat())
    await state.set_state(NewTaskFlow.estimate)
    await reply(event, texts.NEW_TASK_ESTIMATE, new_task_estimate_keyboard())


@on_date_chosen(PURPOSE_DUE)
async def _due_changed(event: Message | CallbackQuery, state: FSMContext, due: datetime,
                       data: dict[str, Any]) -> None:
    flow = await state.get_data()
    await state.clear()
    tasks: TaskService = data["tasks"]
    user: User = data["current_user"]
    task_id = int(flow["due_task_id"])
    try:
        task = await tasks.change_due(user, task_id, due)
    except (PermissionDenied, NotFound):
        await reply(event, texts.PERMISSION_DENIED)
        return
    except InvalidTransition:
        await reply(event, texts.TASK_STATE_CHANGED)
        return
    except ValidationFailed as exc:
        await reply(event, texts.VALIDATION_MESSAGES.get(exc.code, texts.GENERIC_ERROR))
        return
    await reply(event, texts.TASK_DUE_CHANGED.format(code=esc(task.code), due=format_jalali_datetime(due)))
    message = event.message if isinstance(event, CallbackQuery) else event
    if isinstance(message, Message):
        await send_card(message, tasks, user, task_id, data["clock"])


# ---- estimate (F17) ----------------------------------------------------------------


@router.callback_query(NewTaskFlow.estimate, NewTaskCb.filter(F.step == NewTaskStep.ESTIMATE))
async def on_estimate_button(
    query: CallbackQuery, callback_data: NewTaskCb, state: FSMContext, tasks: TaskService
) -> None:
    minutes = int(callback_data.value) if callback_data.value.isdigit() else 0
    await _ask_series(query, state, tasks, minutes or None)
    await query.answer()


@router.message(NewTaskFlow.estimate, FREE_TEXT)
async def on_estimate_text(message: Message, state: FSMContext, tasks: TaskService) -> None:
    try:
        minutes = parse_estimate_input(message.text or "")
    except InvalidEstimateInput:
        await message.answer(texts.INVALID_ESTIMATE)
        return
    await _ask_series(message, state, tasks, minutes)


async def _ask_series(
    event: Message | CallbackQuery, state: FSMContext, tasks: TaskService, minutes: int | None
) -> None:
    await state.update_data(estimated_minutes=minutes)
    await state.set_state(NewTaskFlow.series)
    await reply(event, texts.NEW_TASK_SERIES, new_task_series_keyboard(await tasks.active_series()))


# ---- series / chain / confirm ----------------------------------------------------


@router.callback_query(NewTaskFlow.series, NewTaskCb.filter(F.step == NewTaskStep.SERIES))
async def on_series(query: CallbackQuery, callback_data: NewTaskCb, state: FSMContext, tasks: TaskService) -> None:
    series_id = int(callback_data.value) if callback_data.value.isdigit() else 0
    if series_id and series_id not in {s.id for s in await tasks.active_series()}:
        await query.answer(texts.VALIDATION_MESSAGES["series_invalid"], show_alert=True)
        return
    await state.update_data(series_id=series_id or None)
    await state.set_state(NewTaskFlow.chain)
    await reply(query, texts.NEW_TASK_CHAIN, new_task_chain_keyboard())
    await query.answer()


@router.callback_query(NewTaskFlow.chain, NewTaskCb.filter(F.step == NewTaskStep.CHAIN))
async def on_chain(query: CallbackQuery, callback_data: NewTaskCb, state: FSMContext, tasks: TaskService) -> None:
    try:
        chain = ApprovalChain(callback_data.value)
    except ValueError:
        await query.answer(texts.STALE_BUTTON, show_alert=True)
        return
    await state.update_data(approval_chain=chain.value)
    await state.set_state(NewTaskFlow.confirm)
    await reply(query, await _summary(state, tasks), new_task_confirm_keyboard())
    await query.answer()


async def _summary(state: FSMContext, tasks: TaskService) -> str:
    data = await state.get_data()
    users = {u.id: u for u in await tasks.assignable_users()}
    series = {s.id: s for s in await tasks.active_series()}
    description = esc(data["description"]) if data.get("description") else texts.NO_DESCRIPTION
    if data.get("attachments"):
        description = f"{description} + {texts.NEW_TASK_BRIEF_FILE}"
    series_obj = series.get(data.get("series_id") or 0)
    return texts.NEW_TASK_CONFIRM.format(
        title=esc(data["title"]),
        assignee=user_label(users.get(data["assignee_id"])),
        due=format_jalali_datetime(datetime.fromisoformat(data["due_at"])),
        series=esc(series_obj.name) if series_obj else texts.NO_SERIES,
        chain=texts.CHAIN_LABELS[ApprovalChain(data["approval_chain"])],
        estimate=format_minutes(data.get("estimated_minutes")),
        description=description,
    )


@router.callback_query(NewTaskFlow.confirm, NewTaskCb.filter(F.step == NewTaskStep.CREATE))
async def on_create(
    query: CallbackQuery, state: FSMContext, tasks: TaskService, current_user: User, clock: Clock
) -> None:
    data = await state.get_data()
    await state.clear()
    new = NewTask(
        title=data["title"],
        assignee_id=int(data["assignee_id"]),
        due_at=datetime.fromisoformat(data["due_at"]),
        description=data.get("description"),
        attachments=list(data.get("attachments") or []),
        series_id=data.get("series_id"),
        approval_chain=ApprovalChain(data["approval_chain"]),
        estimated_minutes=data.get("estimated_minutes"),
    )
    try:
        task = await tasks.create_generic(current_user, new)
    except PermissionDenied:
        await reply(query, texts.PERMISSION_DENIED)
        await query.answer()
        return
    except ValidationFailed as exc:
        await reply(query, texts.VALIDATION_MESSAGES.get(exc.code, texts.GENERIC_ERROR))
        await query.answer()
        return
    done = texts.TASK_CREATED_SELF if task.assignee_id == current_user.id else texts.TASK_CREATED
    await reply(query, done.format(code=esc(task.code)))
    await query.answer()
    if isinstance(query.message, Message):
        await send_card(query.message, tasks, current_user, task.id, clock)


# ---- abort / stale -------------------------------------------------------------


@router.callback_query(NewTaskCb.filter(F.step == NewTaskStep.ABORT))
async def on_abort(query: CallbackQuery, state: FSMContext, current_user: User, admin_views: AdminViews) -> None:
    await state.clear()
    await reply(query, texts.FLOW_ABORTED)
    await query.answer()
    if isinstance(query.message, Message):
        await query.message.answer(texts.MENU_SHOWN, reply_markup=menu_for(current_user, admin_views))


@router.callback_query(NewTaskCb.filter())
async def on_stale_flow_button(query: CallbackQuery) -> None:
    await query.answer(texts.STALE_BUTTON, show_alert=True)
