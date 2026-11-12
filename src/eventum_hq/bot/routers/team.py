"""👥 Team menu: delegation of final approval (F7, M2), recurring tasks (F10, M5),
members and offboarding (F15, M6 — see ``routers/members.py``).

Changing roles, capabilities and weekly capacity is Backlog B1 (not in v0).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from eventum_hq.bot import texts
from eventum_hq.bot.formatters import fa_digits, format_jalali_datetime, user_label
from eventum_hq.bot.keyboards.main_menu import AdminViews, menu_for
from eventum_hq.bot.keyboards.members import team_members_rows
from eventum_hq.bot.keyboards.recurrences import recurrences_button_row
from eventum_hq.bot.keyboards.tasks import (
    TeamAction,
    TeamCb,
    delegate_pick_keyboard,
    team_keyboard,
)
from eventum_hq.bot.routers.dates import on_date_chosen, start_date_input
from eventum_hq.bot.states import PURPOSE_DELEGATION
from eventum_hq.bot.task_ui import reply
from eventum_hq.core.errors import AlreadyDecided, NotFound, PermissionDenied, ValidationFailed
from eventum_hq.models import Capability, User
from eventum_hq.services.delegations import DelegationService
from eventum_hq.services.offboarding import OffboardingService
from eventum_hq.services.permissions import MenuItem, can_use_menu_item, has_capability

router = Router(name="team")


async def _team_text(delegations: DelegationService, offboarding: OffboardingService,
                     user: User) -> tuple[str, int | None, int]:
    current = await delegations.current()
    if current is None:
        status, active_id = texts.TEAM_NO_DELEGATION, None
    else:
        status = texts.TEAM_DELEGATION_ACTIVE.format(
            to_name=user_label(current.to_user), ends=format_jalali_datetime(current.delegation.ends_at)
        )
        active_id = current.delegation.id
    text = texts.TEAM_MENU.format(delegation=status)
    pending = 0
    if has_capability(user, Capability.MANAGE_USERS):
        pending = len(await offboarding.pending_handovers(user))
        orphans = await offboarding.orphan_recurrences(user)
        if pending:
            text += texts.TEAM_PENDING_HANDOVERS.format(count=fa_digits(pending))
        if orphans:
            text += texts.TEAM_ORPHAN_RECURRENCES.format(count=fa_digits(orphans))
    return text + texts.TEAM_MORE_SOON, active_id, pending


def _team_markup(user: User, active_id: int | None, pending: int) -> InlineKeyboardMarkup:
    markup = team_keyboard(can_delegate=has_capability(user, Capability.DELEGATE), active_delegation_id=active_id)
    if has_capability(user, Capability.MANAGE_USERS):  # 👤 members and offboarding (F15, M6)
        markup.inline_keyboard[:0] = team_members_rows(pending)
    if has_capability(user, Capability.CREATE_TASK):  # 🔁 recurring tasks (F10, M5)
        markup.inline_keyboard.append(recurrences_button_row())
    return markup


@router.message(F.text == texts.MENU_LABELS[MenuItem.TEAM])
async def menu_team(message: Message, state: FSMContext, current_user: User, delegations: DelegationService,
                    admin_views: AdminViews, offboarding: OffboardingService) -> None:
    await state.clear()
    if not can_use_menu_item(current_user, MenuItem.TEAM):
        await message.answer(texts.PERMISSION_DENIED, reply_markup=menu_for(current_user, admin_views))
        return
    text, active_id, pending = await _team_text(delegations, offboarding, current_user)
    await message.answer(text, reply_markup=_team_markup(current_user, active_id, pending))


@router.callback_query(TeamCb.filter())
async def on_team(query: CallbackQuery, callback_data: TeamCb, state: FSMContext, current_user: User,
                  delegations: DelegationService, offboarding: OffboardingService) -> None:
    action = callback_data.action
    can_delegate = has_capability(current_user, Capability.DELEGATE)
    if not can_use_menu_item(current_user, MenuItem.TEAM) or (action != TeamAction.HOME and not can_delegate):
        await query.answer(texts.PERMISSION_DENIED, show_alert=True)
        return

    if action == TeamAction.HOME:
        await state.clear()
        text, active_id, pending = await _team_text(delegations, offboarding, current_user)
        await reply(query, text, _team_markup(current_user, active_id, pending))
    elif action == TeamAction.NEW_DELEGATION:
        candidates = await delegations.candidates()
        if not candidates:
            await query.answer(texts.DELEGATION_NO_CANDIDATES, show_alert=True)
            return
        await reply(query, texts.DELEGATION_PICK, delegate_pick_keyboard(candidates))
    elif action == TeamAction.PICK_DELEGATE:
        await state.clear()
        await start_date_input(query, state, PURPOSE_DELEGATION, texts.DELEGATION_END_PROMPT,
                               time_prompt=texts.TIME_PROMPT, delegate_id=callback_data.arg)
    elif action == TeamAction.REVOKE:
        try:
            await delegations.revoke(current_user, callback_data.arg)
        except AlreadyDecided:
            await query.answer(texts.DELEGATION_ALREADY_ENDED, show_alert=True)
            return
        except (PermissionDenied, NotFound):
            await query.answer(texts.PERMISSION_DENIED, show_alert=True)
            return
        text, active_id, pending = await _team_text(delegations, offboarding, current_user)
        await reply(query, texts.DELEGATION_REVOKED + "\n\n" + text,
                    _team_markup(current_user, active_id, pending))
    await query.answer()


@on_date_chosen(PURPOSE_DELEGATION)
async def _delegation_end_chosen(event: Message | CallbackQuery, state: FSMContext, ends: datetime,
                                 data: dict[str, Any]) -> None:
    flow = await state.get_data()
    await state.clear()
    delegations: DelegationService = data["delegations"]
    try:
        delegation = await delegations.create(data["current_user"], int(flow["delegate_id"]), ends)
    except PermissionDenied:
        await reply(event, texts.PERMISSION_DENIED)
        return
    except ValidationFailed as exc:
        await reply(event, texts.VALIDATION_MESSAGES.get(exc.code, texts.GENERIC_ERROR))
        return
    current = await delegations.current()
    name = user_label(current.to_user) if current is not None else ""
    await reply(event, texts.DELEGATION_CREATED.format(ends=format_jalali_datetime(delegation.ends_at), name=name))
