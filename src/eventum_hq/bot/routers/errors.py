"""Global error handler (handoff §6.4): log with traceback, tell the user, alert SYSTEM_ADMINs.

The alert is rate-limited to one message per error type per 10 minutes
(see :meth:`SystemService.report_error`).
"""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.types import ErrorEvent

from eventum_hq.bot import texts
from eventum_hq.bot.outbox import OutboxSender
from eventum_hq.services.system import SystemService

router = Router(name="errors")
log = logging.getLogger(__name__)


def _where(event: ErrorEvent) -> str:
    update = event.update
    if update.message is not None:
        text = update.message.text or ""
        return "command " + text.split()[0] if text.startswith("/") else "message"
    if update.callback_query is not None:
        data = update.callback_query.data or ""
        return "button " + data.split(":")[0]  # only the prefix: ids are not useful here
    return update.event_type or "update"


@router.errors()
async def on_error(event: ErrorEvent, system: SystemService | None = None,
                   outbox: OutboxSender | None = None) -> bool:
    log.error("unhandled error in update %s", event.update.update_id, exc_info=event.exception)
    if system is not None and await system.report_error(
        type(event.exception).__name__, _where(event), str(event.exception)
    ) and outbox is not None:
        # aiogram's error middleware sits outside OutboxFlushMiddleware, so flush here
        try:
            await outbox.flush_urgent()
        except Exception:
            log.exception("could not flush the error alert")
    update = event.update
    try:
        if update.message is not None and update.message.chat.type == "private":
            await update.message.answer(texts.ERROR_REPORTED)
        elif update.callback_query is not None:
            await update.callback_query.answer(texts.ERROR_REPORTED, show_alert=True)
    except Exception:
        log.exception("could not report the error to the user")
    return True
