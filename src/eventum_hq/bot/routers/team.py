"""👥 Team menu. M2: temporary delegation of final approval (F7).

Users, roles, weekly capacity and offboarding are added in later milestones.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from eventum_hq.bot import texts
from eventum_hq.bot.formatters import format_jalali_datetime, user_label
from eventum_hq.bot.keyboards.main_menu import AdminViews, menu_for
from eventum_hq.bot.keyboards.tasks import (
    TeamAction,
    TeamCb,
    delegate_pick_keyboard,
    quick_date_keyboard,
    team_keyboard,
)
from eventum_hq.bot.states import PURPOSE_DELEGATION, DateInput
from eventum_hq.bot.task_ui import reply
from eventum_hq.core.errors import AlreadyDecided, NotFound, PermissionDenied
from eventum_hq.models import Capability, User
from eventum_hq.services.delegations import DelegationService
from eventum_hq.services.permissions import MenuItem, can_use_menu_item, has_capability

router = Router(name="team")


async def _team_text(delegations: DelegationService) -> tuple[str, int | None]:
    current = await delegations.current()
    if current is None:
        status, active_id = texts.TEAM_NO_DELEGATION, None
    else:
        status = texts.TEAM_DELEGATION_ACTIVE.format(
            to_name=user_label(current.to_user), ends=format_jalali_datetime(current.delegation.ends_at)
        )
        active_id = current.delegation.id
    return texts.TEAM_MENU.format(delegation=status) + texts.TEAM_MORE_SOON, active_id


@router.message(F.text == texts.MENU_LABELS[MenuItem.TEAM])
async def menu_team(message: Message, state: FSMContext, current_user: User, delegations: DelegationService,
                    admin_views: AdminViews) -> None:
    await state.clear()
    if not can_use_menu_item(current_user, MenuItem.TEAM):
        await message.answer(texts.PERMISSION_DENIED, reply_markup=menu_for(current_user, admin_views))
        return
    text, active_id = await _team_text(delegations)
    await message.answer(text, reply_markup=team_keyboard(
        can_delegate=has_capability(current_user, Capability.DELEGATE), active_delegation_id=active_id))


@router.callback_query(TeamCb.filter())
async def on_team(query: CallbackQuery, callback_data: TeamCb, state: FSMContext, current_user: User,
                  delegations: DelegationService) -> None:
    action = callback_data.action
    can_delegate = has_capability(current_user, Capability.DELEGATE)
    if not can_use_menu_item(current_user, MenuItem.TEAM) or (action != TeamAction.HOME and not can_delegate):
        await query.answer(texts.PERMISSION_DENIED, show_alert=True)
        return

    if action == TeamAction.HOME:
        await state.clear()
        text, active_id = await _team_text(delegations)
        await reply(query, text, team_keyboard(can_delegate=can_delegate, active_delegation_id=active_id))
    elif action == TeamAction.NEW_DELEGATION:
        candidates = await delegations.candidates()
        if not candidates:
            await query.answer(texts.DELEGATION_NO_CANDIDATES, show_alert=True)
            return
        await reply(query, texts.DELEGATION_PICK, delegate_pick_keyboard(candidates))
    elif action == TeamAction.PICK_DELEGATE:
        await state.clear()
        await state.update_data(date_purpose=PURPOSE_DELEGATION, delegate_id=callback_data.arg)
        await state.set_state(DateInput.date)
        await reply(query, texts.DELEGATION_END_PROMPT, quick_date_keyboard())
    elif action == TeamAction.REVOKE:
        try:
            await delegations.revoke(current_user, callback_data.arg)
        except AlreadyDecided:
            await query.answer(texts.DELEGATION_ALREADY_ENDED, show_alert=True)
            return
        except (PermissionDenied, NotFound):
            await query.answer(texts.PERMISSION_DENIED, show_alert=True)
            return
        text, active_id = await _team_text(delegations)
        await reply(query, texts.DELEGATION_REVOKED + "\n\n" + text,
                    team_keyboard(can_delegate=can_delegate, active_delegation_id=active_id))
    await query.answer()
