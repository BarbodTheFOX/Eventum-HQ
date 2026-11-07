"""Access flow buttons.

* Applicant: role picker (``JoinCb``) → access request.
* OWNER: card buttons (``AccessCb``) → approve as requested / with another role / reject.
"""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from eventum_hq.bot import texts
from eventum_hq.bot.formatters import access_request_card, display_name, role_label
from eventum_hq.bot.keyboards.access import (
    AccessAction,
    AccessCb,
    JoinCb,
    access_pick_role_keyboard,
    access_request_keyboard,
)
from eventum_hq.bot.keyboards.main_menu import AdminViews, menu_for
from eventum_hq.core.errors import AlreadyDecided, InvalidRole, NotFound, PermissionDenied
from eventum_hq.models import User
from eventum_hq.services.users import RequestResult, UserService

router = Router(name="access")
log = logging.getLogger(__name__)


# ---- applicant -----------------------------------------------------------------


@router.callback_query(JoinCb.filter())
async def on_role_picked(
    query: CallbackQuery,
    callback_data: JoinCb,
    users: UserService,
    admin_views: AdminViews,
    current_user: User | None,
) -> None:
    tg = query.from_user
    try:
        outcome = await users.request_access(
            telegram_id=tg.id, full_name=tg.full_name, username=tg.username, role=callback_data.role
        )
    except InvalidRole:
        await query.answer(texts.INVALID_ROLE, show_alert=True)
        return

    if outcome.result == RequestResult.REQUEST_SENT:
        text = texts.ACCESS_REQUEST_SENT.format(role=role_label(outcome.user.role))
    elif outcome.result == RequestResult.ALREADY_REQUESTED:
        text = texts.ACCESS_REQUEST_ALREADY_SENT
    else:
        text = texts.ALREADY_MEMBER
    await _edit(query, text, None)
    await query.answer()
    if outcome.result == RequestResult.ALREADY_MEMBER and isinstance(query.message, Message):
        await query.message.answer(texts.MENU_SHOWN, reply_markup=menu_for(outcome.user, admin_views))


# ---- OWNER ---------------------------------------------------------------------


@router.callback_query(AccessCb.filter())
async def on_access_button(
    query: CallbackQuery, callback_data: AccessCb, users: UserService, current_user: User
) -> None:
    action, user_id = callback_data.action, callback_data.user_id
    try:
        if action in (AccessAction.PICK_ROLE, AccessAction.BACK):
            target = await users.pending_request(current_user, user_id)
            markup = (
                access_pick_role_keyboard(user_id)
                if action == AccessAction.PICK_ROLE
                else access_request_keyboard(user_id, target.role)
            )
            hint = texts.ACCESS_PICK_ROLE_HINT if action == AccessAction.PICK_ROLE else ""
            await _edit(query, _card(target) + hint, markup)
            await query.answer()
            return

        if action == AccessAction.REJECT:
            target = await users.reject_access(current_user, user_id)
            suffix = texts.ACCESS_CARD_REJECTED_SUFFIX.format(
                actor=display_name(current_user.full_name)
            )
        else:
            role = callback_data.role if action == AccessAction.APPROVE_AS else None
            target = await users.approve_access(current_user, user_id, role)
            suffix = texts.ACCESS_CARD_APPROVED_SUFFIX.format(
                role=role_label(target.role), actor=display_name(current_user.full_name)
            )
    except PermissionDenied:
        await query.answer(texts.PERMISSION_DENIED, show_alert=True)
        return
    except NotFound:
        await query.answer(texts.NOT_FOUND, show_alert=True)
        return
    except InvalidRole:
        await query.answer(texts.INVALID_ROLE, show_alert=True)
        return
    except AlreadyDecided as exc:
        await query.answer(texts.ACCESS_ALREADY_DECIDED, show_alert=True)
        target_now = await users.get(user_id)
        if target_now is not None:
            status = texts.ACCESS_STATUS_LABELS.get(exc.current_status or "", exc.current_status)
            await _edit(query, _card(target_now) + texts.ACCESS_CARD_CURRENT_STATUS.format(status=status), None)
        return

    await _edit(query, _card(target) + suffix, None)
    await query.answer()


def _card(target: User) -> str:
    return access_request_card(
        full_name=target.full_name,
        username=target.username,
        telegram_id=target.telegram_id,
        role=target.role,
    )


async def _edit(query: CallbackQuery, text: str, markup: InlineKeyboardMarkup | None) -> None:
    if not isinstance(query.message, Message):
        return
    try:
        await query.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as exc:  # e.g. "message is not modified"
        log.debug("could not edit message: %s", exc)
