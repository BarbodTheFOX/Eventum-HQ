"""👀 / ✅ review queues, the review card, approve, and change-request notes (handoff §4.8)."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from eventum_hq.bot import texts
from eventum_hq.bot.attachments import extract_attachment
from eventum_hq.bot.formatters import display_name, esc, fa_digits, review_card, task_list_text
from eventum_hq.bot.keyboards.main_menu import AdminViews, menu_for
from eventum_hq.bot.keyboards.tasks import (
    NotesAction,
    NotesCb,
    ReviewAction,
    ReviewCb,
    notes_keyboard,
    review_keyboard,
    review_queue_keyboard,
)
from eventum_hq.bot.states import ReviewNotesFlow
from eventum_hq.bot.task_ui import FREE_TEXT, reply, send_card
from eventum_hq.core.errors import AlreadyDecided, NotFound, PermissionDenied, ValidationFailed
from eventum_hq.core.timeutil import Clock
from eventum_hq.integrations.telegram_archive import TelegramArchive
from eventum_hq.models import ReviewStage, User
from eventum_hq.services.permissions import MenuItem
from eventum_hq.services.reviews import ReviewService, ReviewView
from eventum_hq.services.tasks import TaskService

router = Router(name="review")
log = logging.getLogger(__name__)

_LABEL = texts.MENU_LABELS
QUEUE_LIMIT = 30


# ---- queues ------------------------------------------------------------------------


@router.message(F.text == _LABEL[MenuItem.REVIEW_QUEUE])
async def menu_l1_queue(message: Message, state: FSMContext, current_user: User, reviews: ReviewService,
                        clock: Clock, admin_views: AdminViews) -> None:
    await _show_queue(message, state, current_user, reviews, clock, admin_views, ReviewStage.L1)


@router.message(F.text == _LABEL[MenuItem.APPROVAL_QUEUE])
async def menu_final_queue(message: Message, state: FSMContext, current_user: User, reviews: ReviewService,
                           clock: Clock, admin_views: AdminViews) -> None:
    await _show_queue(message, state, current_user, reviews, clock, admin_views, ReviewStage.FINAL)


async def _show_queue(message: Message, state: FSMContext, user: User, reviews: ReviewService, clock: Clock,
                      admin_views: AdminViews, stage: ReviewStage) -> None:
    await state.clear()
    try:
        rows = await reviews.queue(user, stage)
    except PermissionDenied:
        await message.answer(texts.PERMISSION_DENIED, reply_markup=menu_for(user, admin_views))
        return
    if not rows:
        await message.answer(texts.QUEUE_EMPTY, reply_markup=menu_for(user, admin_views))
        return
    rows = rows[:QUEUE_LIMIT]
    header = (texts.QUEUE_L1_HEADER if stage == ReviewStage.L1 else texts.QUEUE_FINAL_HEADER).format(
        count=fa_digits(len(rows))
    )
    now = clock.now()
    await message.answer(task_list_text(header, rows, now), reply_markup=review_queue_keyboard(rows, now))


# ---- review card ---------------------------------------------------------------------


async def send_review_card(message: Message, view: ReviewView, archive: TelegramArchive, now, prefix: str = "") -> None:  # type: ignore[no-untyped-def]
    await message.answer(
        prefix + review_card(view, now),
        reply_markup=review_keyboard(view.task.id, view.submission.id, view.submission.version, str(view.stage)),
    )
    for attachment in view.submission.attachments:
        try:
            await archive.send_to(message.chat.id, attachment)
        except TelegramAPIError as exc:
            log.warning("could not send file to reviewer: %s", exc)


@router.callback_query(ReviewCb.filter(F.action == ReviewAction.OPEN))
async def on_open(query: CallbackQuery, callback_data: ReviewCb, current_user: User, reviews: ReviewService,
                  archive: TelegramArchive, clock: Clock) -> None:
    try:
        view = await reviews.review_view(current_user, callback_data.submission_id)
    except AlreadyDecided:
        await query.answer(texts.REVIEW_ALREADY_DONE, show_alert=True)
        return
    except (PermissionDenied, NotFound):
        await query.answer(texts.PERMISSION_DENIED, show_alert=True)
        return
    await query.answer()
    if isinstance(query.message, Message):
        await send_review_card(query.message, view, archive, clock.now())


@router.callback_query(ReviewCb.filter(F.action == ReviewAction.APPROVE))
async def on_approve(query: CallbackQuery, callback_data: ReviewCb, current_user: User,
                     reviews: ReviewService) -> None:
    try:
        await reviews.approve(current_user, callback_data.submission_id, callback_data.version,
                              callback_data.stage)
    except AlreadyDecided:
        await query.answer(texts.REVIEW_ALREADY_DONE, show_alert=True)
        await _close_card(query, "")
        return
    except (PermissionDenied, NotFound, ValueError):
        await query.answer(texts.PERMISSION_DENIED, show_alert=True)
        return
    await query.answer(texts.APPROVED_OK)
    await _close_card(query, texts.REVIEW_APPROVED_SUFFIX.format(actor=display_name(current_user.full_name)))


async def _close_card(query: CallbackQuery, suffix: str) -> None:
    """Remove the decision buttons (and append the decision) on the review card."""
    if not isinstance(query.message, Message):
        return
    try:
        if suffix and query.message.html_text:
            await query.message.edit_text(query.message.html_text + suffix, reply_markup=None)
        else:
            await query.message.edit_reply_markup(reply_markup=None)
    except TelegramAPIError as exc:
        log.debug("could not close review card: %s", exc)


@router.callback_query(ReviewCb.filter(F.action == ReviewAction.CHANGES))
async def on_changes(query: CallbackQuery, callback_data: ReviewCb, state: FSMContext, current_user: User,
                     reviews: ReviewService) -> None:
    try:
        task = await reviews.task_for_submission(callback_data.submission_id)
    except NotFound:
        await query.answer(texts.REVIEW_ALREADY_DONE, show_alert=True)
        return
    await state.clear()
    await state.set_state(ReviewNotesFlow.collect)
    await state.update_data(submission_id=callback_data.submission_id, version=callback_data.version,
                            stage=callback_data.stage, code=task.code, texts=[], files=[])
    await query.answer()
    if isinstance(query.message, Message):
        await query.message.answer(texts.NOTES_PROMPT.format(code=esc(task.code)), reply_markup=notes_keyboard())


@router.callback_query(ReviewCb.filter(F.action == ReviewAction.DETAILS))
async def on_details(query: CallbackQuery, callback_data: ReviewCb, current_user: User, tasks: TaskService,
                     clock: Clock) -> None:
    try:
        if isinstance(query.message, Message):
            await send_card(query.message, tasks, current_user, callback_data.submission_id, clock)
    except (PermissionDenied, NotFound):
        await query.answer(texts.PERMISSION_DENIED, show_alert=True)
        return
    await query.answer()


# ---- change notes -------------------------------------------------------------------


async def _notes_ack(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    count = len(data["texts"]) + len(data["files"])
    await message.answer(texts.NOTES_COLLECTED.format(count=fa_digits(count)), reply_markup=notes_keyboard())


@router.message(ReviewNotesFlow.collect, FREE_TEXT)
async def on_note_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.update_data(texts=data["texts"] + [(message.text or "").strip()])
    await _notes_ack(message, state)


@router.message(ReviewNotesFlow.collect, ~F.text)
async def on_note_media(message: Message, state: FSMContext) -> None:
    attachment = extract_attachment(message)
    if attachment is None:
        await message.answer(texts.NOTES_UNSUPPORTED)
        return
    data = await state.get_data()
    caption = (message.caption or "").strip()
    await state.update_data(files=data["files"] + [attachment],
                            texts=data["texts"] + ([caption] if caption else []))
    await _notes_ack(message, state)


@router.callback_query(ReviewNotesFlow.collect, NotesCb.filter(F.action == NotesAction.DONE))
async def on_notes_done(query: CallbackQuery, state: FSMContext, current_user: User,
                        reviews: ReviewService) -> None:
    data = await state.get_data()
    if not data["texts"] and not data["files"]:
        await query.answer(texts.NOTES_EMPTY, show_alert=True)
        return
    try:
        await reviews.request_changes(
            current_user, int(data["submission_id"]), int(data["version"]), data["stage"],
            note_text="\n\n".join(t for t in data["texts"] if t) or None,
            note_attachments=list(data["files"]),
        )
    except AlreadyDecided:
        await state.clear()
        await query.answer(texts.REVIEW_ALREADY_DONE, show_alert=True)
        return
    except (PermissionDenied, NotFound, ValueError):
        await state.clear()
        await query.answer(texts.PERMISSION_DENIED, show_alert=True)
        return
    except ValidationFailed as exc:
        await query.answer(texts.VALIDATION_MESSAGES.get(exc.code, texts.GENERIC_ERROR), show_alert=True)
        return
    await state.clear()
    await query.answer()
    await reply(query, texts.CHANGES_SENT.format(code=esc(data["code"])))


@router.callback_query(NotesCb.filter(F.action == NotesAction.ABORT))
async def on_notes_abort(query: CallbackQuery, state: FSMContext, current_user: User,
                         admin_views: AdminViews) -> None:
    await state.clear()
    await query.answer()
    await reply(query, texts.FLOW_ABORTED)
    if isinstance(query.message, Message):
        await query.message.answer(texts.MENU_SHOWN, reply_markup=menu_for(current_user, admin_views))


@router.callback_query(NotesCb.filter())
async def on_notes_stale(query: CallbackQuery) -> None:
    await query.answer(texts.STALE_BUTTON, show_alert=True)
