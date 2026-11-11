"""🎬 Reels (handoff §4.5): ➕ new reel flow, reel card / R-code, 🖼 cover photos,
🚀 ready-to-publish list and publish registration.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from eventum_hq.bot import texts
from eventum_hq.bot.attachments import extract_attachment
from eventum_hq.bot.formatters import (
    esc,
    fa_digits,
    format_jalali_date,
    format_jalali_datetime,
    format_minutes,
    reel_card,
    user_label,
)
from eventum_hq.bot.keyboards.main_menu import AdminViews, menu_for
from eventum_hq.bot.keyboards.reels import (
    PhotosAction,
    PhotosCb,
    PublishAction,
    PublishCb,
    ReelAction,
    ReelCardCb,
    ReelCb,
    ReelStep,
    assignee_keyboard,
    confirm_keyboard,
    deadline_pick_keyboard,
    edit_type_keyboard,
    estimate_key_keyboard,
    estimate_keyboard,
    photos_keyboard,
    publish_keyboard,
    ready_list_keyboard,
    reel_card_keyboard,
    reel_cancel_confirm_keyboard,
    series_keyboard,
    subtype_keyboard,
)
from eventum_hq.bot.routers.dates import on_date_chosen, start_date_input
from eventum_hq.bot.states import (
    PURPOSE_PUBLISHED_AT,
    PURPOSE_REEL_DEADLINE,
    PURPOSE_REEL_PUBLISH,
    NewReelFlow,
    PhotosFlow,
    PublishFlow,
)
from eventum_hq.bot.task_ui import FREE_TEXT, reply, send_card
from eventum_hq.core.errors import InvalidTransition, NotFound, PermissionDenied, ValidationFailed
from eventum_hq.core.jalali import InvalidEstimateInput, parse_estimate_input, tehran_today
from eventum_hq.core.timeutil import Clock
from eventum_hq.integrations.telegram_archive import ArchiveNotConfigured, TelegramArchive
from eventum_hq.models import Capability, ContentSubtype, User
from eventum_hq.services.permissions import MenuItem, has_capability
from eventum_hq.services.reels import TEXT_MAX, TITLE_MAX, NewReel, ReelService, parse_reel_code
from eventum_hq.services.tasks import TaskService

router = Router(name="reels")
log = logging.getLogger(__name__)

_LABEL = texts.MENU_LABELS
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_MAX_PHOTOS = 20


# ======================================================================================
# ➕ new reel
# ======================================================================================


@router.message(F.text == _LABEL[MenuItem.NEW_REEL])
async def menu_new_reel(message: Message, state: FSMContext, current_user: User, admin_views: AdminViews) -> None:
    await state.clear()
    if not has_capability(current_user, Capability.CREATE_REEL):
        await message.answer(texts.PERMISSION_DENIED, reply_markup=menu_for(current_user, admin_views))
        return
    await state.set_state(NewReelFlow.title)
    await message.answer(texts.NEW_REEL_TITLE)


@router.message(NewReelFlow.title, FREE_TEXT)
async def on_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if not title or len(title) > TITLE_MAX:
        await message.answer(texts.VALIDATION_MESSAGES["title_empty" if not title else "title_too_long"])
        return
    await state.update_data(title=title)
    await state.set_state(NewReelFlow.subtype)
    await message.answer(texts.NEW_REEL_SUBTYPE, reply_markup=subtype_keyboard())


@router.callback_query(NewReelFlow.subtype, ReelCb.filter(F.step == ReelStep.SUBTYPE))
async def on_subtype(query: CallbackQuery, callback_data: ReelCb, state: FSMContext, reels: ReelService,
                     tasks: TaskService) -> None:
    try:
        subtype = ContentSubtype(callback_data.value)
    except ValueError:
        await query.answer(texts.STALE_BUTTON, show_alert=True)
        return
    await state.update_data(subtype=subtype.value, motion=False)
    if subtype == ContentSubtype.NORMAL:
        await state.set_state(NewReelFlow.edit_type)
        await reply(query, texts.NEW_REEL_EDIT_TYPE, edit_type_keyboard())
    else:
        await _ask_series(query, state, reels, tasks)
    await query.answer()


@router.callback_query(NewReelFlow.edit_type, ReelCb.filter(F.step == ReelStep.EDIT_TYPE))
async def on_edit_type(query: CallbackQuery, callback_data: ReelCb, state: FSMContext, reels: ReelService,
                       tasks: TaskService) -> None:
    await state.update_data(motion=callback_data.value == "motion")
    await _ask_series(query, state, reels, tasks)
    await query.answer()


async def _ask_series(event: Message | CallbackQuery, state: FSMContext, reels: ReelService,
                      tasks: TaskService) -> None:
    data = await state.get_data()
    defaults = await reels.defaults()
    default = defaults.trial_series if data["subtype"] == ContentSubtype.TRIAL.value else defaults.series
    await state.set_state(NewReelFlow.series)
    await reply(event, texts.NEW_REEL_SERIES,
                series_keyboard(await tasks.active_series(), default.id if default else None))


@router.callback_query(NewReelFlow.series, ReelCb.filter(F.step == ReelStep.SERIES))
async def on_series(query: CallbackQuery, callback_data: ReelCb, state: FSMContext) -> None:
    series_id = int(callback_data.value) if callback_data.value.isdigit() else 0
    await state.update_data(series_id=series_id or None)
    await start_date_input(query, state, PURPOSE_REEL_PUBLISH, texts.NEW_REEL_PUBLISH_PROMPT,
                           time_prompt=texts.TIME_PROMPT)
    await query.answer()


@on_date_chosen(PURPOSE_REEL_PUBLISH)
async def _publish_time_chosen(event: Message | CallbackQuery, state: FSMContext, when: datetime,
                               data: dict[str, Any]) -> None:
    await state.update_data(publish_at=when.isoformat())
    await state.set_state(NewReelFlow.timecodes)
    await reply(event, texts.NEW_REEL_TIMECODES)


@router.message(NewReelFlow.timecodes, FREE_TEXT)
async def on_timecodes(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()[:TEXT_MAX]
    await state.update_data(timecodes=text)
    await state.set_state(NewReelFlow.cover_text)
    await message.answer(texts.NEW_REEL_COVER_TEXT)


@router.message(NewReelFlow.cover_text, FREE_TEXT)
async def on_cover_text(message: Message, state: FSMContext, reels: ReelService, tasks: TaskService) -> None:
    await state.update_data(cover_text=(message.text or "").strip()[:TEXT_MAX])
    defaults = await reels.defaults()
    users = await tasks.assignable_users()
    await state.set_state(NewReelFlow.edit_assignee)
    await message.answer(texts.NEW_REEL_EDIT_ASSIGNEE, reply_markup=assignee_keyboard(
        users, defaults.edit_assignee.id if defaults.edit_assignee else None, ReelStep.EDIT_ASSIGNEE))


@router.message(NewReelFlow.timecodes, ~F.text)
@router.message(NewReelFlow.cover_text, ~F.text)
@router.message(NewReelFlow.title, ~F.text)
async def on_need_text(message: Message) -> None:
    await message.answer(texts.REEL_TEXT_REQUIRED)


@router.callback_query(NewReelFlow.edit_assignee, ReelCb.filter(F.step == ReelStep.EDIT_ASSIGNEE))
async def on_edit_assignee(query: CallbackQuery, callback_data: ReelCb, state: FSMContext, reels: ReelService,
                           tasks: TaskService) -> None:
    users = await tasks.assignable_users()
    if not callback_data.value.isdigit() or int(callback_data.value) not in {u.id for u in users}:
        await query.answer(texts.VALIDATION_MESSAGES["assignee_inactive"], show_alert=True)
        return
    await state.update_data(edit_assignee_id=int(callback_data.value))
    defaults = await reels.defaults()
    await state.set_state(NewReelFlow.cover_assignee)
    await reply(query, texts.NEW_REEL_COVER_ASSIGNEE, assignee_keyboard(
        users, defaults.cover_assignee.id if defaults.cover_assignee else None, ReelStep.COVER_ASSIGNEE))
    await query.answer()


@router.callback_query(NewReelFlow.cover_assignee, ReelCb.filter(F.step == ReelStep.COVER_ASSIGNEE))
async def on_cover_assignee(query: CallbackQuery, callback_data: ReelCb, state: FSMContext, reels: ReelService,
                            tasks: TaskService) -> None:
    users = await tasks.assignable_users()
    if not callback_data.value.isdigit() or int(callback_data.value) not in {u.id for u in users}:
        await query.answer(texts.VALIDATION_MESSAGES["assignee_inactive"], show_alert=True)
        return
    await state.update_data(cover_assignee_id=int(callback_data.value))
    await _show_summary(query, state, reels, tasks)
    await query.answer()


async def _show_summary(event: Message | CallbackQuery, state: FSMContext, reels: ReelService,
                        tasks: TaskService) -> None:
    await state.set_state(NewReelFlow.confirm)
    data = await state.get_data()
    subtype = ContentSubtype(data["subtype"])
    plan = await reels.plan(datetime.fromisoformat(data["publish_at"]), subtype, bool(data.get("motion")))
    users = {u.id: u for u in await tasks.assignable_users()}
    series = {s.id: s for s in await tasks.active_series()}

    def when(key: str, default: datetime) -> str:
        return format_jalali_datetime(datetime.fromisoformat(data[key]) if data.get(key) else default)

    series_obj = series.get(data.get("series_id") or 0)
    text = texts.NEW_REEL_CONFIRM.format(
        title=esc(data["title"]),
        subtype=texts.SUBTYPE_LABELS[subtype.value],
        series=esc(series_obj.name) if series_obj else texts.NO_SERIES,
        publish=format_jalali_datetime(datetime.fromisoformat(data["publish_at"])),
        editor=user_label(users.get(data["edit_assignee_id"])),
        designer=user_label(users.get(data["cover_assignee_id"])),
        edit_due=when("edit_due_at", plan.edit_due_at),
        cover_due=when("cover_due_at", plan.cover_due_at),
        photos_due=when("photos_due_at", plan.photos_due_at),
        edit_est=format_minutes(data.get("edit_estimate") or plan.edit_estimate),
        cover_est=format_minutes(data.get("cover_estimate") or plan.cover_estimate),
        timecodes=esc(data["timecodes"]),
        cover_text=esc(data["cover_text"]),
    )
    await reply(event, text, confirm_keyboard())


# ---- change deadlines / estimates from the summary ----------------------------------


@router.callback_query(NewReelFlow.confirm, ReelCb.filter(F.step == ReelStep.DEADLINES))
async def on_deadlines(query: CallbackQuery) -> None:
    await reply(query, texts.PICK_DEADLINE, deadline_pick_keyboard())
    await query.answer()


@router.callback_query(NewReelFlow.confirm, ReelCb.filter(F.step == ReelStep.DEADLINE))
async def on_deadline_key(query: CallbackQuery, callback_data: ReelCb, state: FSMContext) -> None:
    key = callback_data.value
    if key not in texts.DEADLINE_KEY_LABELS:
        await query.answer(texts.STALE_BUTTON, show_alert=True)
        return
    await start_date_input(query, state, PURPOSE_REEL_DEADLINE,
                           texts.DEADLINE_PROMPT.format(label=texts.DEADLINE_KEY_LABELS[key]), deadline_key=key)
    await query.answer()


@on_date_chosen(PURPOSE_REEL_DEADLINE)
async def _deadline_chosen(event: Message | CallbackQuery, state: FSMContext, when: datetime,
                           data: dict[str, Any]) -> None:
    key = (await state.get_data())["deadline_key"]
    await state.update_data({f"{key}_due_at": when.isoformat()})
    await _show_summary(event, state, data["reels"], data["tasks"])


@router.callback_query(NewReelFlow.confirm, ReelCb.filter(F.step == ReelStep.ESTIMATES))
async def on_estimates(query: CallbackQuery) -> None:
    await reply(query, texts.PICK_ESTIMATE, estimate_key_keyboard())
    await query.answer()


@router.callback_query(NewReelFlow.confirm, ReelCb.filter(F.step == ReelStep.ESTIMATE_KEY))
async def on_estimate_key(query: CallbackQuery, callback_data: ReelCb, state: FSMContext) -> None:
    key = callback_data.value
    if key not in ("edit", "cover"):
        await query.answer(texts.STALE_BUTTON, show_alert=True)
        return
    await state.update_data(estimate_key=key)
    await state.set_state(NewReelFlow.estimate)
    await reply(query, texts.ESTIMATE_PROMPT.format(label=texts.DEADLINE_KEY_LABELS[key]), estimate_keyboard())
    await query.answer()


@router.callback_query(NewReelFlow.estimate, ReelCb.filter(F.step == ReelStep.ESTIMATE))
async def on_estimate_button(query: CallbackQuery, callback_data: ReelCb, state: FSMContext, reels: ReelService,
                             tasks: TaskService) -> None:
    if not callback_data.value.isdigit():
        await query.answer(texts.STALE_BUTTON, show_alert=True)
        return
    await _set_estimate(query, state, reels, tasks, int(callback_data.value))
    await query.answer()


@router.message(NewReelFlow.estimate, FREE_TEXT)
async def on_estimate_text(message: Message, state: FSMContext, reels: ReelService, tasks: TaskService) -> None:
    try:
        minutes = parse_estimate_input(message.text or "")
    except InvalidEstimateInput:
        await message.answer(texts.INVALID_ESTIMATE)
        return
    await _set_estimate(message, state, reels, tasks, minutes)


async def _set_estimate(event: Message | CallbackQuery, state: FSMContext, reels: ReelService, tasks: TaskService,
                        minutes: int) -> None:
    key = (await state.get_data())["estimate_key"]
    await state.update_data({f"{key}_estimate": minutes})
    await _show_summary(event, state, reels, tasks)


@router.callback_query(NewReelFlow.confirm, ReelCb.filter(F.step == ReelStep.BACK))
@router.callback_query(NewReelFlow.estimate, ReelCb.filter(F.step == ReelStep.BACK))
async def on_back(query: CallbackQuery, state: FSMContext, reels: ReelService, tasks: TaskService) -> None:
    await _show_summary(query, state, reels, tasks)
    await query.answer()


@router.callback_query(NewReelFlow.confirm, ReelCb.filter(F.step == ReelStep.CREATE))
async def on_create(query: CallbackQuery, state: FSMContext, current_user: User, reels: ReelService,
                    tasks: TaskService) -> None:
    data = await state.get_data()

    def dt(key: str) -> datetime | None:
        return datetime.fromisoformat(data[key]) if data.get(key) else None

    new = NewReel(
        title=data["title"],
        subtype=ContentSubtype(data["subtype"]),
        planned_publish_at=datetime.fromisoformat(data["publish_at"]),
        timecodes=data["timecodes"],
        cover_text=data["cover_text"],
        edit_assignee_id=int(data["edit_assignee_id"]),
        cover_assignee_id=int(data["cover_assignee_id"]),
        series_id=data.get("series_id"),
        motion=bool(data.get("motion")),
        photos_due_at=dt("photos_due_at"),
        edit_due_at=dt("edit_due_at"),
        cover_due_at=dt("cover_due_at"),
        edit_estimate=data.get("edit_estimate"),
        cover_estimate=data.get("cover_estimate"),
    )
    try:
        item = await reels.create(current_user, new)
    except PermissionDenied:
        await state.clear()
        await query.answer(texts.PERMISSION_DENIED, show_alert=True)
        return
    except ValidationFailed as exc:  # keep the flow so the user can fix it
        await query.answer(texts.VALIDATION_MESSAGES.get(exc.code, texts.GENERIC_ERROR), show_alert=True)
        return
    await state.clear()
    await query.answer()
    await reply(query, texts.REEL_CREATED.format(code=esc(item.code)))
    if isinstance(query.message, Message):
        await _send_reel_card(query.message, reels, current_user, item.id)


@router.callback_query(ReelCb.filter(F.step == ReelStep.ABORT))
async def on_abort(query: CallbackQuery, state: FSMContext, current_user: User, admin_views: AdminViews) -> None:
    await state.clear()
    await query.answer()
    await reply(query, texts.FLOW_ABORTED)
    if isinstance(query.message, Message):
        await query.message.answer(texts.MENU_SHOWN, reply_markup=menu_for(current_user, admin_views))


@router.callback_query(ReelCb.filter())
async def on_stale_reel_button(query: CallbackQuery) -> None:
    await query.answer(texts.STALE_BUTTON, show_alert=True)


# ======================================================================================
# reel card, R-code, cancel
# ======================================================================================


async def _send_reel_card(message: Message, reels: ReelService, viewer: User, item_id: int,
                          prefix: str = "", archive: TelegramArchive | None = None) -> None:
    view = await reels.view(viewer, item_id=item_id)
    await message.answer(prefix + reel_card(view), reply_markup=reel_card_keyboard(view))
    if archive is not None and view.can_publish:
        for attachment in await reels.final_files(item_id):
            try:
                await archive.send_to(message.chat.id, attachment)
            except TelegramAPIError as exc:
                log.warning("could not send a final file: %s", exc)


@router.message(F.text.func(lambda text: parse_reel_code(text) is not None))
async def on_reel_code(message: Message, current_user: User, reels: ReelService, archive: TelegramArchive) -> None:
    code = parse_reel_code(message.text) or ""
    try:
        view = await reels.view(current_user, code=code)
    except NotFound:
        await message.answer(texts.REEL_CODE_NOT_FOUND.format(code=esc(code)))
        return
    except PermissionDenied:
        await message.answer(texts.PERMISSION_DENIED)
        return
    await _send_reel_card(message, reels, current_user, view.item.id, archive=archive)


@router.callback_query(ReelCardCb.filter())
async def on_reel_button(query: CallbackQuery, callback_data: ReelCardCb, state: FSMContext, current_user: User,
                         reels: ReelService, archive: TelegramArchive) -> None:
    item_id = callback_data.item_id
    try:
        if callback_data.action == ReelAction.OPEN:
            await query.answer()
            if isinstance(query.message, Message):
                await _send_reel_card(query.message, reels, current_user, item_id, archive=archive)
            return
        view = await reels.view(current_user, item_id=item_id)
        if callback_data.action == ReelAction.CANCEL_ASK:
            if not view.can_cancel:
                raise PermissionDenied("reel.cancel")
            await reply(query, reel_card(view) + texts.CONFIRM_CANCEL_REEL, reel_cancel_confirm_keyboard(item_id))
            await query.answer()
        elif callback_data.action == ReelAction.CANCEL_YES:
            await reels.cancel(current_user, item_id)
            view = await reels.view(current_user, item_id=item_id)
            await reply(query, reel_card(view), reel_card_keyboard(view))
            await query.answer(texts.REEL_CANCELLED_OK)
        elif callback_data.action == ReelAction.PUBLISH:
            if not view.can_publish:
                raise PermissionDenied("reel.publish")
            await state.clear()
            await state.set_state(PublishFlow.links)
            await state.update_data(item_id=item_id, code=view.item.code, links=[])
            await query.answer()
            if isinstance(query.message, Message):
                await query.message.answer(texts.PUBLISH_PROMPT.format(code=esc(view.item.code)),
                                           reply_markup=publish_keyboard())
    except (PermissionDenied, NotFound):
        await query.answer(texts.PERMISSION_DENIED, show_alert=True)
    except InvalidTransition:
        await query.answer(texts.TASK_STATE_CHANGED, show_alert=True)


# ======================================================================================
# 🚀 ready to publish + publish
# ======================================================================================


@router.message(F.text == _LABEL[MenuItem.READY_TO_PUBLISH])
async def menu_ready(message: Message, state: FSMContext, current_user: User, reels: ReelService,
                     admin_views: AdminViews) -> None:
    await state.clear()
    try:
        views = await reels.ready_list(current_user)
    except PermissionDenied:
        await message.answer(texts.PERMISSION_DENIED, reply_markup=menu_for(current_user, admin_views))
        return
    if not views:
        await message.answer(texts.READY_EMPTY, reply_markup=menu_for(current_user, admin_views))
        return
    await message.answer(texts.READY_HEADER.format(count=fa_digits(len(views))),
                         reply_markup=ready_list_keyboard(views))


@router.message(PublishFlow.links, FREE_TEXT)
async def on_publish_links(message: Message, state: FSMContext) -> None:
    links = _URL_RE.findall(message.text or "")
    data = await state.get_data()
    all_links = data["links"] + links
    await state.update_data(links=all_links)
    await message.answer(texts.PUBLISH_COLLECTED.format(count=fa_digits(len(all_links))),
                         reply_markup=publish_keyboard())


@router.callback_query(PublishFlow.links, PublishCb.filter(F.action == PublishAction.NOW))
async def on_publish_now(query: CallbackQuery, state: FSMContext, current_user: User, reels: ReelService) -> None:
    await _publish(query, state, current_user, reels, None)


@router.callback_query(PublishFlow.links, PublishCb.filter(F.action == PublishAction.OTHER_TIME))
async def on_publish_other_time(query: CallbackQuery, state: FSMContext) -> None:
    if not (await state.get_data())["links"]:
        await query.answer(texts.PUBLISH_NO_LINKS, show_alert=True)
        return
    await start_date_input(query, state, PURPOSE_PUBLISHED_AT, texts.PUBLISH_TIME_PROMPT,
                           time_prompt=texts.TIME_PROMPT)
    await query.answer()


@on_date_chosen(PURPOSE_PUBLISHED_AT)
async def _published_at_chosen(event: Message | CallbackQuery, state: FSMContext, when: datetime,
                               data: dict[str, Any]) -> None:
    await _publish(event, state, data["current_user"], data["reels"], when)


async def _publish(event: Message | CallbackQuery, state: FSMContext, user: User, reels: ReelService,
                   when: datetime | None) -> None:
    data = await state.get_data()
    if not data["links"]:
        if isinstance(event, CallbackQuery):
            await event.answer(texts.PUBLISH_NO_LINKS, show_alert=True)
        return
    try:
        item = await reels.publish(user, int(data["item_id"]), data["links"], when)
    except ValidationFailed as exc:
        await reply(event, texts.VALIDATION_MESSAGES.get(exc.code, texts.GENERIC_ERROR), publish_keyboard())
        return
    except (PermissionDenied, NotFound, InvalidTransition):
        await state.clear()
        await reply(event, texts.TASK_STATE_CHANGED)
        return
    await state.clear()
    if isinstance(event, CallbackQuery):
        await event.answer()
    await reply(event, texts.PUBLISHED_OK.format(code=esc(item.code)))


@router.callback_query(PublishCb.filter(F.action == PublishAction.ABORT))
@router.callback_query(PhotosCb.filter(F.action == PhotosAction.ABORT))
async def on_flow_abort(query: CallbackQuery, state: FSMContext, current_user: User, admin_views: AdminViews) -> None:
    await state.clear()
    await query.answer()
    await reply(query, texts.FLOW_ABORTED)
    if isinstance(query.message, Message):
        await query.message.answer(texts.MENU_SHOWN, reply_markup=menu_for(current_user, admin_views))


# ======================================================================================
# 🖼 cover photos (from the edit task card)
# ======================================================================================


async def start_photos(query: CallbackQuery, state: FSMContext, edit_task_id: int, reel_code: str,
                       title: str) -> None:
    await state.clear()
    await state.set_state(PhotosFlow.collect)
    await state.update_data(edit_task_id=edit_task_id, reel_code=reel_code, title=title, items=[])
    if isinstance(query.message, Message):
        await query.message.answer(texts.PHOTOS_PROMPT.format(code=esc(reel_code)), reply_markup=photos_keyboard())


@router.message(PhotosFlow.collect, ~F.text)
async def on_photo(message: Message, state: FSMContext) -> None:
    attachment = extract_attachment(message)
    if attachment is None:
        await message.answer(texts.SUBMIT_UNSUPPORTED)
        return
    data = await state.get_data()
    if len(data["items"]) >= _MAX_PHOTOS:
        await message.answer(texts.VALIDATION_MESSAGES["submission_too_big"])
        return
    items = data["items"] + [{"attachment": attachment, "chat_id": message.chat.id, "message_id": message.message_id}]
    await state.update_data(items=items)
    await message.answer(texts.PHOTOS_COLLECTED.format(count=fa_digits(len(items))), reply_markup=photos_keyboard())


@router.callback_query(PhotosFlow.collect, PhotosCb.filter(F.action == PhotosAction.DONE))
async def on_photos_done(query: CallbackQuery, state: FSMContext, current_user: User, reels: ReelService,
                         tasks: TaskService, archive: TelegramArchive, clock: Clock) -> None:
    data = await state.get_data()
    if not data["items"]:
        await query.answer(texts.PHOTOS_EMPTY, show_alert=True)
        return
    if not archive.configured:
        await query.answer()
        await reply(query, texts.ARCHIVE_NOT_CONFIGURED, photos_keyboard())
        return
    caption = texts.ARCHIVE_PHOTOS_CAPTION.format(
        code_tag=str(data["reel_code"]).replace("-", ""),
        title=data["title"],
        sender=user_label(current_user, html=False),
        date=format_jalali_date(tehran_today(clock.now())),
    )
    attachments = []
    try:
        for item in data["items"]:
            attachment = dict(item["attachment"])
            attachment["archive_message_id"] = await archive.copy_in(
                item["chat_id"], item["message_id"], caption, attachment.get("type"))
            attachments.append(attachment)
    except (TelegramAPIError, ArchiveNotConfigured) as exc:
        log.warning("archive copy of cover photos failed: %s", exc)
        await query.answer()
        await reply(query, texts.ARCHIVE_COPY_FAILED, photos_keyboard())
        return
    edit_task_id = int(data["edit_task_id"])
    try:
        await reels.deliver_cover_photos(current_user, edit_task_id, attachments)
    except (PermissionDenied, NotFound):
        await state.clear()
        await query.answer(texts.PERMISSION_DENIED, show_alert=True)
        return
    except InvalidTransition:
        await state.clear()
        await query.answer(texts.TASK_STATE_CHANGED, show_alert=True)
        return
    await state.clear()
    await query.answer()
    await reply(query, texts.PHOTOS_DONE)
    if isinstance(query.message, Message):
        await send_card(query.message, tasks, current_user, edit_task_id, clock)


@router.callback_query(PhotosCb.filter())
@router.callback_query(PublishCb.filter())
async def on_stale(query: CallbackQuery) -> None:
    await query.answer(texts.STALE_BUTTON, show_alert=True)
