"""The bot stays only in TEAM_GROUP_ID; it leaves any other group it is added to."""

from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.filters import JOIN_TRANSITION, ChatMemberUpdatedFilter
from aiogram.types import ChatMemberUpdated

from eventum_hq.bot.middlewares import should_leave_chat

router = Router(name="groups")
log = logging.getLogger(__name__)


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=JOIN_TRANSITION))
async def on_bot_added(event: ChatMemberUpdated, bot: Bot, team_group_id: int | None) -> None:
    chat = event.chat
    if should_leave_chat(chat_type=chat.type, chat_id=chat.id, team_group_id=team_group_id):
        log.warning("added to a foreign group chat_id=%s — leaving", chat.id)
        await bot.leave_chat(chat.id)
    else:
        log.info("bot membership changed chat_id=%s type=%s", chat.id, chat.type)
