"""``/health`` and ``/backup`` (handoff §5.2, §6.4, §6.5): SYSTEM_ADMIN holders and the OWNER only."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import FSInputFile, Message

from eventum_hq.bot import texts
from eventum_hq.bot.formatters import esc, fa_digits, format_jalali_date, health_text
from eventum_hq.core.errors import PermissionDenied, ValidationFailed
from eventum_hq.core.timeutil import Clock, to_tehran
from eventum_hq.models import User
from eventum_hq.services.system import SystemService

router = Router(name="system")
log = logging.getLogger(__name__)


@router.message(Command("health"))
async def cmd_health(message: Message, current_user: User, system: SystemService) -> None:
    try:
        report = await system.health(current_user)
    except PermissionDenied:
        await message.answer(texts.PERMISSION_DENIED)
        return
    await message.answer(health_text(report))


@router.message(Command("backup"))
async def cmd_backup(message: Message, current_user: User, system: SystemService, clock: Clock) -> None:
    try:
        await system.health(current_user)  # permission check before any work
    except PermissionDenied:
        await message.answer(texts.PERMISSION_DENIED)
        return
    await message.answer(texts.BACKUP_STARTED)
    try:
        packed = await system.backup_now(current_user)
    except ValidationFailed as exc:
        await message.answer(texts.VALIDATION_MESSAGES.get(exc.code, texts.GENERIC_ERROR))
        return
    if not packed.sendable:
        size_mb = round(packed.size / (1024 * 1024), 1)
        await message.answer(texts.BACKUP_TOO_BIG_MANUAL.format(size=fa_digits(size_mb), path=esc(packed.path)))
        return
    caption = texts.BACKUP_MANUAL_CAPTION.format(date=format_jalali_date(to_tehran(clock.now()).date()))
    try:
        await message.answer_document(FSInputFile(packed.path), caption=caption)
    except TelegramAPIError as exc:
        log.warning("could not send the manual backup: %s", exc)
        await message.answer(texts.BACKUP_TOO_BIG_MANUAL.format(size="?", path=esc(packed.path)))
