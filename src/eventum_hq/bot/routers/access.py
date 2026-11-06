"""OWNER's approve/reject buttons on an access-request card."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from eventum_hq.bot import texts
from eventum_hq.bot.formatters import access_request_card, display_name
from eventum_hq.bot.keyboards.access import AccessAction, AccessCb
from eventum_hq.core.errors import AlreadyDecided, NotFound, PermissionDenied
from eventum_hq.models import User
from eventum_hq.services.users import UserService

router = Router(name="access")
log = logging.getLogger(__name__)


@router.callback_query(AccessCb.filter(F.action.in_(set(AccessAction))))
async def on_access_decision(
    query: CallbackQuery, callback_data: AccessCb, users: UserService, current_user: User
) -> None:
    approve = callback_data.action == AccessAction.APPROVE
    try:
        if approve:
            target = await users.approve_access(current_user, callback_data.user_id)
        else:
            target = await users.reject_access(current_user, callback_data.user_id)
    except PermissionDenied:
        await query.answer(texts.PERMISSION_DENIED, show_alert=True)
        return
    except NotFound:
        await query.answer(texts.NOT_FOUND, show_alert=True)
        return
    except AlreadyDecided as exc:
        await query.answer(texts.ACCESS_ALREADY_DECIDED, show_alert=True)
        target_now = await users.get(callback_data.user_id)
        if target_now is not None:
            status = texts.ACCESS_STATUS_LABELS.get(exc.current_status or "", exc.current_status)
            await _close_card(query, target_now, texts.ACCESS_CARD_CURRENT_STATUS.format(status=status))
        return

    suffix = texts.ACCESS_CARD_APPROVED_SUFFIX if approve else texts.ACCESS_CARD_REJECTED_SUFFIX
    await _close_card(query, target, suffix.format(actor=display_name(current_user.full_name)))
    await query.answer()


async def _close_card(query: CallbackQuery, target: User, suffix: str) -> None:
    """Rewrite the card with the decision and remove its buttons."""
    if not isinstance(query.message, Message):
        return
    text = access_request_card(
        full_name=target.full_name, username=target.username, telegram_id=target.telegram_id
    )
    try:
        await query.message.edit_text(text + suffix, reply_markup=None)
    except TelegramBadRequest as exc:  # e.g. "message is not modified"
        log.debug("could not edit access card: %s", exc)
