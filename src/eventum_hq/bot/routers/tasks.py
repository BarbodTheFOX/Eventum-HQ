"""📋 My tasks, 🗂 All tasks, the task card and its actions, and T-xxxx lookup."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from eventum_hq.bot import texts
from eventum_hq.bot.attachments import send_attachment
from eventum_hq.bot.formatters import esc, history_text, task_list_text, user_label
from eventum_hq.bot.keyboards.main_menu import AdminViews, menu_for
from eventum_hq.bot.keyboards.tasks import (
    ListCb,
    ListScope,
    TaskAction,
    TaskCb,
    all_tasks_filters_keyboard,
    back_to_card_keyboard,
    cancel_confirm_keyboard,
    page_slice,
    pick_series_keyboard,
    pick_user_keyboard,
    reassign_keyboard,
    task_list_keyboard,
)
from eventum_hq.bot.routers.task_create import start_due_edit, start_new_task
from eventum_hq.bot.task_ui import edit_card, reply, send_card
from eventum_hq.core.errors import InvalidTransition, NotFound, PermissionDenied, ValidationFailed
from eventum_hq.core.timeutil import Clock
from eventum_hq.models import Capability, User
from eventum_hq.services.permissions import MenuItem, has_capability
from eventum_hq.services.tasks import TaskFilter, TaskService, parse_task_code

router = Router(name="tasks")

_LABEL = texts.MENU_LABELS


# ---- menu entries ----------------------------------------------------------------


@router.message(F.text == _LABEL[MenuItem.NEW_TASK])
async def menu_new_task(message: Message, state: FSMContext, current_user: User, admin_views: AdminViews) -> None:
    await start_new_task(message, state, current_user, admin_views)


@router.message(F.text == _LABEL[MenuItem.MY_TASKS])
@router.message(Command("my"))
async def menu_my_tasks(message: Message, state: FSMContext, current_user: User, tasks: TaskService, clock: Clock) -> None:
    await state.clear()
    await _show_list(message, current_user, tasks, clock, ListScope.MY, 0, 0)


@router.message(F.text == _LABEL[MenuItem.ALL_TASKS])
async def menu_all_tasks(message: Message, state: FSMContext, current_user: User, admin_views: AdminViews) -> None:
    await state.clear()
    if not has_capability(current_user, Capability.VIEW_ALL_TASKS):
        await message.answer(texts.PERMISSION_DENIED, reply_markup=menu_for(current_user, admin_views))
        return
    await message.answer(texts.ALL_TASKS_MENU, reply_markup=all_tasks_filters_keyboard())


# ---- lists -------------------------------------------------------------------------


@router.callback_query(ListCb.filter())
async def on_list(query: CallbackQuery, callback_data: ListCb, current_user: User, tasks: TaskService, clock: Clock) -> None:
    scope = callback_data.scope
    try:
        if scope == ListScope.FILTERS:
            _require_view_all(current_user)
            await reply(query, texts.ALL_TASKS_MENU, all_tasks_filters_keyboard())
        elif scope == ListScope.PICK_USER:
            _require_view_all(current_user)
            await reply(query, texts.PICK_PERSON, pick_user_keyboard(await tasks.assignable_users()))
        elif scope == ListScope.PICK_SERIES:
            _require_view_all(current_user)
            await reply(query, texts.PICK_SERIES, pick_series_keyboard(await tasks.active_series()))
        else:
            await _show_list(query, current_user, tasks, clock, scope, callback_data.arg, callback_data.page)
    except PermissionDenied:
        await query.answer(texts.PERMISSION_DENIED, show_alert=True)
        return
    await query.answer()


def _require_view_all(user: User) -> None:
    if not has_capability(user, Capability.VIEW_ALL_TASKS):
        raise PermissionDenied("task.view_all")


async def _show_list(
    event: Message | CallbackQuery, user: User, tasks: TaskService, clock: Clock,
    scope: ListScope, arg: int, page: int,
) -> None:
    now = clock.now()
    if scope == ListScope.MY:
        rows = await tasks.list_my(user)
        if not rows:
            await reply(event, texts.MY_TASKS_EMPTY)
            return
        header = texts.MY_TASKS_HEADER.format(count=len(rows))
    else:
        rows = await tasks.list_all(user, TaskFilter(scope.value), arg or None)
        header = await _list_header(scope, arg, len(rows), tasks)
    on_page, page, pages = page_slice(rows, page)
    await reply(
        event,
        task_list_text(header, on_page, now),
        task_list_keyboard(
            on_page, now, scope=scope, arg=arg, page=page, pages=pages,
            with_filters_button=scope != ListScope.MY,
        ),
    )


async def _list_header(scope: ListScope, arg: int, count: int, tasks: TaskService) -> str:
    if scope == ListScope.OPEN:
        return texts.LIST_HEADER_OPEN.format(count=count)
    if scope == ListScope.OVERDUE:
        return texts.LIST_HEADER_OVERDUE.format(count=count)
    if scope == ListScope.AT_RISK:
        return texts.LIST_HEADER_AT_RISK.format(count=count)
    if scope == ListScope.BY_USER:
        user = next((u for u in await tasks.assignable_users() if u.id == arg), None)
        return texts.LIST_HEADER_USER.format(name=user_label(user), count=count)
    series = next((s for s in await tasks.active_series() if s.id == arg), None)
    return texts.LIST_HEADER_SERIES.format(name=esc(series.name) if series else "—", count=count)


# ---- card actions ------------------------------------------------------------------


@router.callback_query(TaskCb.filter())
async def on_task_button(
    query: CallbackQuery, callback_data: TaskCb, state: FSMContext, bot: Bot,
    current_user: User, tasks: TaskService, clock: Clock,
) -> None:
    action, task_id = callback_data.action, callback_data.task_id
    toast: str | None = None
    try:
        if action == TaskAction.OPEN:
            if callback_data.arg == 1:
                await edit_card(query, tasks, current_user, task_id, clock)
            elif isinstance(query.message, Message):
                await send_card(query.message, tasks, current_user, task_id, clock)
        elif action == TaskAction.START:
            await tasks.start(current_user, task_id)
            await edit_card(query, tasks, current_user, task_id, clock)
            toast = texts.TASK_STARTED
        elif action == TaskAction.CANCEL_ASK:
            view = await tasks.get_view(current_user, task_id=task_id)
            if not view.can_manage:
                raise PermissionDenied("task.cancel")
            await edit_card(query, tasks, current_user, task_id, clock,
                            suffix=texts.CONFIRM_CANCEL_TASK, markup=cancel_confirm_keyboard(task_id))
        elif action == TaskAction.CANCEL_YES:
            await tasks.cancel(current_user, task_id)
            await edit_card(query, tasks, current_user, task_id, clock)
            toast = texts.TASK_CANCELLED
        elif action == TaskAction.DUE:
            view = await tasks.get_view(current_user, task_id=task_id)
            if not view.can_manage:
                raise PermissionDenied("task.edit")
            await start_due_edit(query, state, task_id, view.task.code)
        elif action == TaskAction.REASSIGN:
            view = await tasks.get_view(current_user, task_id=task_id)
            if not view.can_manage:
                raise PermissionDenied("task.reassign")
            users = await tasks.assignable_users()
            await edit_card(query, tasks, current_user, task_id, clock, suffix=texts.REASSIGN_PROMPT,
                            markup=reassign_keyboard(task_id, users, view.task.assignee_id))
        elif action == TaskAction.ASSIGN_TO:
            task = await tasks.reassign(current_user, task_id, callback_data.arg)
            new_assignee = next((u for u in await tasks.assignable_users() if u.id == task.assignee_id), None)
            await edit_card(query, tasks, current_user, task_id, clock)
            toast = texts.TASK_REASSIGNED.format(name=user_label(new_assignee, html=False))
        elif action == TaskAction.HISTORY:
            task, entries = await tasks.history(current_user, task_id)
            await reply(query, history_text(task, entries), back_to_card_keyboard(task_id))
        elif action == TaskAction.BRIEF:
            view = await tasks.get_view(current_user, task_id=task_id)
            if view.brief is not None:
                for attachment in view.brief.attachments:
                    await send_attachment(bot, query.from_user.id, attachment, caption=view.task.code)
    except PermissionDenied:
        await query.answer(texts.PERMISSION_DENIED, show_alert=True)
        return
    except NotFound:
        await query.answer(texts.NOT_FOUND, show_alert=True)
        return
    except InvalidTransition:
        await query.answer(texts.TASK_STATE_CHANGED, show_alert=True)
        try:
            await edit_card(query, tasks, current_user, task_id, clock)
        except (PermissionDenied, NotFound):
            pass
        return
    except ValidationFailed as exc:
        await query.answer(texts.VALIDATION_MESSAGES.get(exc.code, texts.GENERIC_ERROR), show_alert=True)
        return
    await query.answer(toast)


# ---- T-xxxx lookup -------------------------------------------------------------------


@router.message(F.text.func(lambda text: parse_task_code(text) is not None))
async def on_task_code(message: Message, current_user: User, tasks: TaskService, clock: Clock) -> None:
    code = parse_task_code(message.text) or ""
    try:
        view = await tasks.get_view(current_user, code=code)
    except NotFound:
        await message.answer(texts.TASK_CODE_NOT_FOUND.format(code=esc(code)))
        return
    except PermissionDenied:
        await message.answer(texts.PERMISSION_DENIED)
        return
    await send_card(message, tasks, current_user, view.task.id, clock)
