"""Turn Telegram messages into plain attachment dicts and send them back by file_id.

The bot never downloads files; it only stores and re-sends ``file_id`` (so files
over 20 MB work too). Copying into the archive channel arrives in M2.
"""

from __future__ import annotations

from typing import Any

from aiogram import Bot
from aiogram.types import Message


def extract_attachment(message: Message) -> dict[str, Any] | None:
    media: Any = None
    kind = None
    if message.voice:
        media, kind = message.voice, "voice"
    elif message.audio:
        media, kind = message.audio, "audio"
    elif message.video:
        media, kind = message.video, "video"
    elif message.video_note:
        media, kind = message.video_note, "video_note"
    elif message.document:
        media, kind = message.document, "document"
    elif message.photo:
        media, kind = message.photo[-1], "photo"  # largest size
    if media is None:
        return None
    return {
        "type": kind,
        "file_id": media.file_id,
        "file_unique_id": media.file_unique_id,
        "size": getattr(media, "file_size", None),
        "archive_message_id": None,
    }


async def send_attachment(bot: Bot, chat_id: int, attachment: dict[str, Any], caption: str | None = None) -> None:
    file_id = attachment["file_id"]
    kind = attachment.get("type")
    if kind == "voice":
        await bot.send_voice(chat_id, file_id, caption=caption)
    elif kind == "audio":
        await bot.send_audio(chat_id, file_id, caption=caption)
    elif kind == "video":
        await bot.send_video(chat_id, file_id, caption=caption)
    elif kind == "video_note":
        await bot.send_video_note(chat_id, file_id)
    elif kind == "photo":
        await bot.send_photo(chat_id, file_id, caption=caption)
    else:
        await bot.send_document(chat_id, file_id, caption=caption)
