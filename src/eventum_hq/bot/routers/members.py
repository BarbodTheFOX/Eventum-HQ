"""👤 Team members and offboarding (F15, handoff §4.11), opened from «👥 تیم».

Every button is re-checked by :class:`OffboardingService` (``MANAGE_USERS``).
"""

from __future__ import annotations

from aiogram import Router
from aiogram.types import CallbackQuery

from eventum_hq.bot import texts
from eventum_hq.bot.formatters import (
    esc,
    fa_digits,
    handover_text,
    member_card_text,
    offboarding_summary_text,
    user_label,
)
from eventum_hq.bot.keyboards.members import (
    MemberAction,
    MemberCb,
    deactivate_confirm_keyboard,
    member_keyboard,
    members_keyboard,
    pick_target_keyboard,
)
from eventum_hq.bot.task_ui import reply
from eventum_hq.core.errors import InvalidTransition, NotFound, PermissionDenied, ValidationFailed
from eventum_hq.models import User
from eventum_hq.services.offboarding import OffboardingService

router = Router(name="members")


@router.callback_query(MemberCb.filter())
async def on_member(query: CallbackQuery, callback_data: MemberCb, current_user: User,
                    offboarding: OffboardingService) -> None:
    cb = callback_data
    try:
        await _handle(query, cb, current_user, offboarding)
    except PermissionDenied:
        await query.answer(texts.PERMISSION_DENIED, show_alert=True)
        return
    except NotFound:
        await query.answer(texts.NOT_FOUND, show_alert=True)
        return
    except InvalidTransition as exc:
        text = texts.ALREADY_INACTIVE if exc.target == "DEACTIVATE" else texts.TASK_NOT_OPEN
        await query.answer(text, show_alert=True)
        return
    except ValidationFailed as exc:
        await query.answer(texts.VALIDATION_MESSAGES.get(exc.code, texts.GENERIC_ERROR), show_alert=True)
        return
    await query.answer()


async def _handle(query: CallbackQuery, cb: MemberCb, user: User, offboarding: OffboardingService) -> None:
    action = cb.action
    if action == MemberAction.LIST:
        rows = await offboarding.members(user)
        await reply(query, texts.MEMBERS_TITLE.format(count=fa_digits(len(rows))), members_keyboard(rows))
    elif action == MemberAction.HANDOVERS:
        rows = await offboarding.pending_handovers(user)
        await reply(query, texts.MEMBERS_HANDOVER_TITLE, members_keyboard(rows))
    elif action == MemberAction.OPEN:
        await _show_member(query, user, offboarding, cb.arg)
    elif action == MemberAction.DEACT_ASK:
        view = await offboarding.member(user, cb.arg)
        if not view.can_deactivate:
            raise PermissionDenied("deactivate")
        await reply(query, texts.DEACTIVATE_CONFIRM.format(name=user_label(view.user)),
                    deactivate_confirm_keyboard(view.user.id))
    elif action == MemberAction.DEACT_YES:
        view = await offboarding.deactivate(user, cb.arg)
        await reply(query, offboarding_summary_text(view), member_keyboard(view))
    elif action == MemberAction.ALL_PICK:
        view = await offboarding.member(user, cb.arg)
        targets = await offboarding.assignable(user, cb.arg)
        if not targets:
            raise ValidationFailed("no_targets")
        await reply(query, texts.HANDOVER_PICK_ALL.format(count=fa_digits(len(view.open_tasks)),
                                                          name=user_label(view.user)),
                    pick_target_keyboard(targets, MemberAction.ALL_TO, cb.arg, cb.arg))
    elif action == MemberAction.ALL_TO:
        moved = await offboarding.transfer_all(user, cb.arg, cb.to)
        target = await _name(offboarding, user, cb.to)
        await _show_member(query, user, offboarding, cb.arg,
                           prefix=texts.HANDOVER_ALL_DONE.format(count=fa_digits(len(moved)), name=target) + "\n\n")
    elif action == MemberAction.TASK_PICK:
        view = await offboarding.member(user, cb.back)
        task = next((t for t in view.open_tasks if t.id == cb.arg), None)
        if task is None:
            raise InvalidTransition("CLOSED", "REASSIGN")
        targets = await offboarding.assignable(user, cb.back)
        await reply(query, texts.HANDOVER_PICK_TASK.format(code=esc(task.code)),
                    pick_target_keyboard(targets, MemberAction.TASK_TO, task.id, cb.back))
    elif action == MemberAction.TASK_TO:
        task = await offboarding.transfer_task(user, cb.arg, cb.to)
        target = await _name(offboarding, user, cb.to)
        await _show_member(query, user, offboarding, cb.back,
                           prefix=texts.HANDOVER_TASK_DONE.format(code=esc(task.code), name=target) + "\n\n")
    elif action == MemberAction.REC_PICK:
        view = await offboarding.member(user, cb.back)
        recurrence = next((r for r in view.recurrences if r.id == cb.arg), None)
        if recurrence is None:
            raise NotFound("recurrence")
        targets = await offboarding.assignable(user, cb.back)
        await reply(query, texts.HANDOVER_PICK_REC.format(title=esc(recurrence.title)),
                    pick_target_keyboard(targets, MemberAction.REC_TO, recurrence.id, cb.back))
    elif action == MemberAction.REC_TO:
        recurrence = await offboarding.reassign_recurrence(user, cb.arg, cb.to)
        target = await _name(offboarding, user, cb.to)
        await _show_member(query, user, offboarding, cb.back,
                           prefix=texts.HANDOVER_REC_DONE.format(title=esc(recurrence.title), name=target) + "\n\n")


async def _show_member(query: CallbackQuery, user: User, offboarding: OffboardingService, user_id: int,
                       prefix: str = "") -> None:
    view = await offboarding.member(user, user_id)
    text = prefix + member_card_text(view)
    if not view.user.is_active:
        text += handover_text(view)
    await reply(query, text, member_keyboard(view))


async def _name(offboarding: OffboardingService, user: User, user_id: int) -> str:
    view = await offboarding.member(user, user_id)
    return user_label(view.user)
