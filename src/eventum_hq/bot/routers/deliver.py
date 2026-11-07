"""📤 Delivery flow (handoff §4.7): collect files / links / a note, copy files to
the archive channel, then create a versioned Submission.
"""

from __future__ import annotations

import logging
import re

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from eventum_hq.bot import texts
from eventum_hq.bot.attachments import extract_attachment
from eventum_hq.bot.formatters import esc, fa_digits, format_jalali_date, user_label
from eventum_hq.bot.keyboards.main_menu import AdminViews, menu_for
from eventum_hq.bot.keyboards.tasks import SubmitAction, SubmitCb, submit_keyboard
from eventum_hq.bot.states import SubmitFlow
from eventum_hq.bot.task_ui import FREE_TEXT, reply, send_card
from eventum_hq.core.errors import InvalidTransition, NotFound, PermissionDenied, ValidationFailed
from eventum_hq.core.jalali import tehran_today
from eventum_hq.core.timeutil import Clock
from eventum_hq.integrations.telegram_archive import ArchiveNotConfigured, TelegramArchive
from eventum_hq.models import User
from eventum_hq.services.reviews import MAX_FILES, ReviewService
from eventum_hq.services.tasks import TaskService

router = Router(name="deliver")
log = logging.getLogger(__name__)

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


async def start_submit(query: CallbackQuery, state: FSMContext, task_id: int, code: str) -> None:
    await state.clear()
    await state.set_state(SubmitFlow.collect)
    await state.update_data(task_id=task_id, code=code, items=[], links=[], notes=[])
    if isinstance(query.message, Message):
        await query.message.answer(texts.SUBMIT_PROMPT.format(code=esc(code)), reply_markup=submit_keyboard())


async def _ack(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await message.answer(
        texts.SUBMIT_COLLECTED.format(
            files=fa_digits(len(data["items"])),
            links=fa_digits(len(data["links"])),
            note=texts.SUBMIT_COLLECTED_NOTE if data["notes"] else "",
        ),
        reply_markup=submit_keyboard(),
    )


@router.message(SubmitFlow.collect, FREE_TEXT)
async def on_text(message: Message, state: FSMContext) -> None:
    text = message.text or ""
    links = _URL_RE.findall(text)
    note = _URL_RE.sub("", text).strip()
    data = await state.get_data()
    await state.update_data(
        links=data["links"] + links,
        notes=data["notes"] + ([note] if note else []),
    )
    await _ack(message, state)


@router.message(SubmitFlow.collect, ~F.text)
async def on_media(message: Message, state: FSMContext) -> None:
    attachment = extract_attachment(message)
    if attachment is None:
        await message.answer(texts.SUBMIT_UNSUPPORTED)
        return
    data = await state.get_data()
    if len(data["items"]) >= MAX_FILES:
        await message.answer(texts.VALIDATION_MESSAGES["submission_too_big"])
        return
    item = {"attachment": attachment, "chat_id": message.chat.id, "message_id": message.message_id}
    caption = (message.caption or "").strip()
    await state.update_data(
        items=data["items"] + [item],
        links=data["links"] + _URL_RE.findall(caption),
        notes=data["notes"] + ([_URL_RE.sub("", caption).strip()] if _URL_RE.sub("", caption).strip() else []),
    )
    await _ack(message, state)


@router.callback_query(SubmitFlow.collect, SubmitCb.filter(F.action == SubmitAction.SEND))
async def on_send(
    query: CallbackQuery, state: FSMContext, current_user: User, tasks: TaskService,
    reviews: ReviewService, archive: TelegramArchive, clock: Clock,
) -> None:
    data = await state.get_data()
    task_id, code = int(data["task_id"]), str(data["code"])
    items, links = list(data["items"]), list(data["links"])
    if not items and not links:
        await query.answer(texts.SUBMIT_EMPTY, show_alert=True)
        return
    if items and not archive.configured:
        await query.answer()
        await reply(query, texts.ARCHIVE_NOT_CONFIGURED, submit_keyboard())
        return

    try:
        view = await tasks.get_view(current_user, task_id=task_id)
    except (PermissionDenied, NotFound):
        await state.clear()
        await query.answer(texts.PERMISSION_DENIED, show_alert=True)
        return
    version = await reviews.next_version(task_id)
    caption = texts.ARCHIVE_CAPTION.format(
        code_tag=code.replace("-", ""),
        version=version,
        title=view.task.title,
        assignee=user_label(current_user, html=False),
        date=format_jalali_date(tehran_today(clock.now())),
    )
    attachments = []
    try:
        for item in items:
            attachment = dict(item["attachment"])
            attachment["archive_message_id"] = await archive.copy_in(
                item["chat_id"], item["message_id"], caption, attachment.get("type")
            )
            attachments.append(attachment)
    except (TelegramAPIError, ArchiveNotConfigured) as exc:
        log.warning("archive copy failed task=%s: %s", task_id, exc)
        await query.answer()
        await reply(query, texts.ARCHIVE_COPY_FAILED, submit_keyboard())
        return

    try:
        submission = await reviews.submit(
            current_user, task_id, attachments=attachments, links=links,
            note="\n".join(data["notes"]) or None,
        )
    except PermissionDenied:
        await state.clear()
        await query.answer(texts.PERMISSION_DENIED, show_alert=True)
        return
    except InvalidTransition:
        await state.clear()
        await query.answer(texts.TASK_STATE_CHANGED, show_alert=True)
        return
    except ValidationFailed as exc:
        await query.answer(texts.VALIDATION_MESSAGES.get(exc.code, texts.GENERIC_ERROR), show_alert=True)
        return
    await state.clear()
    await query.answer()
    await reply(query, texts.SUBMIT_DONE.format(version=fa_digits(submission.version), code=esc(code)))
    if isinstance(query.message, Message):
        await send_card(query.message, tasks, current_user, task_id, clock)


@router.callback_query(SubmitCb.filter(F.action == SubmitAction.ABORT))
async def on_abort(query: CallbackQuery, state: FSMContext, current_user: User, admin_views: AdminViews) -> None:
    await state.clear()
    await query.answer()
    await reply(query, texts.FLOW_ABORTED)
    if isinstance(query.message, Message):
        await query.message.answer(texts.MENU_SHOWN, reply_markup=menu_for(current_user, admin_views))


@router.callback_query(SubmitCb.filter())
async def on_stale(query: CallbackQuery) -> None:
    await query.answer(texts.STALE_BUTTON, show_alert=True)
