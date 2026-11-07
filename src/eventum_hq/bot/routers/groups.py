"""Bot membership in groups and channels.

* Added to a channel → tell the OWNER its numeric ID (for ARCHIVE_CHANNEL_ID).
* Added to a group while TEAM_GROUP_ID is empty → tell the OWNER its ID and stay.
* Added to a group that is not TEAM_GROUP_ID → leave.
"""

from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import JOIN_TRANSITION, PROMOTED_TRANSITION, ChatMemberUpdatedFilter
from aiogram.types import ChatMemberUpdated

from eventum_hq.bot import texts
from eventum_hq.bot.formatters import esc
from eventum_hq.bot.middlewares import should_leave_chat

router = Router(name="groups")
log = logging.getLogger(__name__)


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=JOIN_TRANSITION))
@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=PROMOTED_TRANSITION))
async def on_bot_added(
    event: ChatMemberUpdated, bot: Bot, team_group_id: int | None, owner_telegram_id: int
) -> None:
    chat = event.chat
    title = esc(chat.title or "")
    if chat.type == "channel":
        log.info("bot added to channel chat_id=%s", chat.id)
        await _tell_owner(bot, owner_telegram_id, texts.CHANNEL_ID_HELP.format(title=title, chat_id=chat.id))
        return
    if chat.type not in ("group", "supergroup"):
        return
    if team_group_id is None:
        log.info("bot added to a group while TEAM_GROUP_ID is empty chat_id=%s", chat.id)
        await _tell_owner(bot, owner_telegram_id, texts.GROUP_ID_HELP.format(title=title, chat_id=chat.id))
        return
    if should_leave_chat(chat_type=chat.type, chat_id=chat.id, team_group_id=team_group_id):
        log.warning("added to a foreign group chat_id=%s — leaving", chat.id)
        await bot.leave_chat(chat.id)
    else:
        log.info("bot is in the team group chat_id=%s", chat.id)


async def _tell_owner(bot: Bot, owner_telegram_id: int, text: str) -> None:
    try:
        await bot.send_message(owner_telegram_id, text)
    except TelegramAPIError as exc:
        log.warning("could not message the owner: %s", exc)
