"""Global error handler (minimal in M0: log + generic message).

The rate-limited alert to SYSTEM_ADMIN is added in M6.
"""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.types import ErrorEvent

from eventum_hq.bot import texts

router = Router(name="errors")
log = logging.getLogger(__name__)


@router.errors()
async def on_error(event: ErrorEvent) -> bool:
    log.error("unhandled error in update %s", event.update.update_id, exc_info=event.exception)
    update = event.update
    try:
        if update.message is not None and update.message.chat.type == "private":
            await update.message.answer(texts.GENERIC_ERROR)
        elif update.callback_query is not None:
            await update.callback_query.answer(texts.GENERIC_ERROR, show_alert=True)
    except Exception:
        log.exception("could not report the error to the user")
    return True
