"""📊 Report on demand (handoff §5.6): the same text as the Saturday 09:00 report."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from eventum_hq.bot import texts
from eventum_hq.bot.keyboards.main_menu import AdminViews, menu_for
from eventum_hq.bot.outbox import report_message, split_text
from eventum_hq.core.errors import PermissionDenied
from eventum_hq.core.timeutil import Clock
from eventum_hq.models import User
from eventum_hq.services.permissions import MenuItem, can_use_menu_item
from eventum_hq.services.reports import ReportService

router = Router(name="reports")


@router.message(F.text == texts.MENU_LABELS[MenuItem.REPORT])
async def menu_report(message: Message, state: FSMContext, current_user: User, reports: ReportService,
                      clock: Clock, admin_views: AdminViews) -> None:
    await state.clear()
    if not can_use_menu_item(current_user, MenuItem.REPORT):
        await message.answer(texts.PERMISSION_DENIED, reply_markup=menu_for(current_user, admin_views))
        return
    try:
        report = await reports.saturday(current_user)
    except PermissionDenied:
        await message.answer(texts.PERMISSION_DENIED, reply_markup=menu_for(current_user, admin_views))
        return
    rendered = report_message(report, clock.now())
    parts = split_text(rendered.text)
    for i, part in enumerate(parts):
        await message.answer(part, reply_markup=rendered.markup if i == len(parts) - 1 else None)
