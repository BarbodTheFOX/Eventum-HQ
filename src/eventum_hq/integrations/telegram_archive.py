"""Private archive channel (handoff §4.7, §6.2).

Every delivered file is copied (``copyMessage``) into ``ARCHIVE_CHANNEL_ID``;
people later receive files *from the archive*, never from each other's chats.
The bot never downloads files, so files over 20 MB work too.

Used only by the bot layer (it needs aiogram); services store the returned
``archive_message_id`` values.
"""

from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot

log = logging.getLogger(__name__)

_NO_CAPTION_TYPES = {"video_note"}


class ArchiveNotConfigured(Exception):
    pass


class TelegramArchive:
    def __init__(self, bot: Bot, channel_id: int | None) -> None:
        self._bot = bot
        self._channel_id = channel_id

    @property
    def configured(self) -> bool:
        return self._channel_id is not None

    async def copy_in(self, from_chat_id: int, message_id: int, caption: str, kind: str | None) -> int:
        """Copy a user's message into the archive. Returns the archive message id."""
        if self._channel_id is None:
            raise ArchiveNotConfigured
        result = await self._bot.copy_message(
            chat_id=self._channel_id,
            from_chat_id=from_chat_id,
            message_id=message_id,
            caption=None if kind in _NO_CAPTION_TYPES else caption,
            parse_mode=None,
        )
        if kind in _NO_CAPTION_TYPES:
            await self._bot.send_message(
                self._channel_id, caption, reply_to_message_id=result.message_id, parse_mode=None
            )
        return result.message_id

    async def send_to(self, chat_id: int, attachment: dict[str, Any], caption: str | None = None) -> None:
        """Send one stored attachment to a user: from the archive if possible, else by file_id."""
        archive_id = attachment.get("archive_message_id")
        if archive_id and self._channel_id is not None:
            await self._bot.copy_message(
                chat_id=chat_id, from_chat_id=self._channel_id, message_id=archive_id
            )
            return
        from eventum_hq.bot.attachments import send_attachment  # local: avoid import cycle

        await send_attachment(self._bot, chat_id, attachment, caption=caption)
