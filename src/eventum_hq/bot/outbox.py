"""Delivers outbox rows written by services.

Urgent rows are delivered right after each update (``OutboxFlushMiddleware``)
and once at startup. The periodic tick, quiet hours and backoff retries come in M5.

A rendered notification is a text message, optionally followed by files
("extras") — e.g. the delivered files under a review card, or a reviewer's
voice notes under a "changes requested" message.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove

from eventum_hq.bot import texts
from eventum_hq.bot.formatters import (
    access_request_card,
    esc,
    fa_digits,
    format_jalali_datetime,
    review_card,
    role_label,
    task_card,
)
from eventum_hq.bot.keyboards.access import access_request_keyboard
from eventum_hq.bot.keyboards.main_menu import main_menu
from eventum_hq.bot.keyboards.tasks import review_keyboard, task_card_keyboard
from eventum_hq.core.timeutil import Clock
from eventum_hq.integrations.telegram_archive import TelegramArchive
from eventum_hq.models import Notification, TaskKind
from eventum_hq.services import delegations as delegation_kinds
from eventum_hq.services import reviews as review_kinds
from eventum_hq.services import tasks as task_kinds
from eventum_hq.services import users as user_kinds
from eventum_hq.services.notifications import OutboxStore
from eventum_hq.services.reviews import ReviewService
from eventum_hq.services.tasks import TaskService
from eventum_hq.services.users import UserService

log = logging.getLogger(__name__)

Markup = InlineKeyboardMarkup | ReplyKeyboardMarkup | ReplyKeyboardRemove | None


class MessageSender(Protocol):
    async def send_message(self, chat_id: int, text: str, **kwargs: Any) -> Any: ...


class UnknownNotificationKind(Exception):
    pass


class UndeliverableNotification(Exception):
    """The notification no longer makes sense (e.g. recipient lost access)."""


@dataclass(slots=True)
class Rendered:
    text: str
    markup: Markup = None
    extras: list[dict[str, Any]] = field(default_factory=list)  # attachments sent after the text


@dataclass(slots=True)
class RenderContext:
    users: UserService
    tasks: TaskService | None = None
    reviews: ReviewService | None = None
    clock: Clock | None = None

    def now(self) -> datetime:
        if self.clock is None:
            raise UnknownNotificationKind("no clock")
        return self.clock.now()


_TASK_CARD_KINDS = {task_kinds.KIND_TASK_ASSIGNED, task_kinds.KIND_TASK_DUE_CHANGED}


async def _recipient(ctx: RenderContext, payload: dict[str, Any]):  # type: ignore[no-untyped-def]
    recipient = await ctx.users.get(int(payload["user_id"]))
    if recipient is None or not recipient.can_use_bot:
        raise UndeliverableNotification("recipient inactive")
    return recipient


async def _task_card(ctx: RenderContext, payload: dict[str, Any], prefix: str) -> Rendered:
    if ctx.tasks is None:
        raise UnknownNotificationKind("no task service")
    recipient = await _recipient(ctx, payload)
    view = await ctx.tasks.get_view(recipient, task_id=int(payload["task_id"]))
    return Rendered(prefix + task_card(view, ctx.now()), task_card_keyboard(view))


async def render(row: Notification, ctx: RenderContext) -> Rendered:
    payload = row.payload or {}
    kind = row.kind
    code = esc(payload.get("code", ""))
    title = esc(payload.get("title", ""))

    # ---- tasks
    if kind in _TASK_CARD_KINDS:
        prefix = texts.NOTIFY_TASK_ASSIGNED if kind == task_kinds.KIND_TASK_ASSIGNED else texts.NOTIFY_TASK_DUE_CHANGED
        return await _task_card(ctx, payload, prefix)
    if kind == task_kinds.KIND_TASK_UNASSIGNED:
        return Rendered(texts.NOTIFY_TASK_UNASSIGNED.format(code=code, title=title))
    if kind == task_kinds.KIND_TASK_CANCELLED:
        return Rendered(texts.NOTIFY_TASK_CANCELLED.format(code=code, title=title))

    # ---- reviews
    if kind == review_kinds.KIND_REVIEW_REQUESTED:
        if ctx.reviews is None:
            raise UnknownNotificationKind("no review service")
        recipient = await _recipient(ctx, payload)
        view = await ctx.reviews.review_view(recipient, int(payload["task_id"]))
        return Rendered(
            texts.NOTIFY_REVIEW_REQUESTED + review_card(view, ctx.now()),
            review_keyboard(view.task.id, view.submission.id, view.submission.version, str(view.stage)),
            list(view.submission.attachments),
        )
    if kind == review_kinds.KIND_REVIEW_L1_APPROVED:
        return Rendered(texts.NOTIFY_L1_APPROVED.format(code=code, title=title))
    if kind == review_kinds.KIND_REVIEW_APPROVED:
        if ctx.tasks is None:
            raise UnknownNotificationKind("no task service")
        recipient = await _recipient(ctx, payload)
        view = await ctx.tasks.get_view(recipient, task_id=int(payload["task_id"]))
        prefix = (texts.NOTIFY_APPROVED if view.task.kind == TaskKind.GENERIC else texts.NOTIFY_APPROVED_FINAL)
        return Rendered(prefix.format(code=code) + task_card(view, ctx.now()), task_card_keyboard(view))
    if kind == review_kinds.KIND_REVIEW_CHANGES:
        if ctx.reviews is None or ctx.tasks is None:
            raise UnknownNotificationKind("no review service")
        recipient = await _recipient(ctx, payload)
        review, task = await ctx.reviews.review_detail(recipient, int(payload["review_id"]))
        view = await ctx.tasks.get_view(recipient, task_id=task.id)
        text = texts.NOTIFY_CHANGES.format(code=code, round=fa_digits(task.revision_round))
        if review.note_text:
            text += texts.NOTIFY_CHANGES_NOTE.format(note=esc(review.note_text))
        if review.note_attachments:
            text += texts.NOTIFY_CHANGES_FILES.format(count=fa_digits(len(review.note_attachments)))
        return Rendered(text + task_card(view, ctx.now()), task_card_keyboard(view),
                        list(review.note_attachments))
    if kind == review_kinds.KIND_TASK_DONE:
        return Rendered(texts.NOTIFY_TASK_DONE.format(code=code, title=title))

    # ---- delegations
    if kind in (delegation_kinds.KIND_DELEGATION_STARTED, delegation_kinds.KIND_DELEGATION_REVOKED):
        fmt = (texts.NOTIFY_DELEGATION_STARTED if kind == delegation_kinds.KIND_DELEGATION_STARTED
               else texts.NOTIFY_DELEGATION_REVOKED)
        return Rendered(fmt.format(
            from_name=esc(payload.get("from_name") or ""),
            to_name=esc(payload.get("to_name") or ""),
            ends=format_jalali_datetime(datetime.fromisoformat(payload["ends_at"])),
        ))

    # ---- access
    if kind == user_kinds.KIND_ACCESS_REQUEST:
        requested_role = payload["requested_role"]
        text = access_request_card(
            full_name=payload.get("full_name"),
            username=payload.get("username"),
            telegram_id=int(payload["telegram_id"]),
            role=requested_role,
        )
        return Rendered(text, access_request_keyboard(int(payload["user_id"]), requested_role))
    if kind == user_kinds.KIND_ACCESS_APPROVED:
        user = await ctx.users.get(int(payload["user_id"]))
        if user is None or not user.can_use_bot:
            raise UndeliverableNotification("approved user is no longer active")
        return Rendered(texts.ACCESS_APPROVED_FOR_USER.format(role=role_label(user.role)), main_menu(user))
    if kind == user_kinds.KIND_ACCESS_REJECTED:
        return Rendered(texts.ACCESS_REJECTED_FOR_USER, ReplyKeyboardRemove())
    raise UnknownNotificationKind(kind)


class OutboxSender:
    def __init__(
        self,
        sender: MessageSender,
        store: OutboxStore,
        users: UserService,
        tasks: TaskService | None = None,
        clock: Clock | None = None,
        reviews: ReviewService | None = None,
        archive: TelegramArchive | None = None,
    ) -> None:
        self._sender = sender
        self._store = store
        self._ctx = RenderContext(users=users, tasks=tasks, reviews=reviews, clock=clock)
        self._archive = archive
        self._lock = asyncio.Lock()  # never deliver the same row twice in parallel

    async def flush_urgent(self) -> int:
        """Send every due urgent row. Returns the number sent successfully."""
        sent = 0
        async with self._lock:
            for row in await self._store.due_urgent():
                if await self._deliver(row):
                    sent += 1
        return sent

    async def _deliver(self, row: Notification) -> bool:
        try:
            rendered = await render(row, self._ctx)
        except Exception as exc:  # broken payload / unknown kind / no longer relevant: do not retry
            log.warning("outbox render failed id=%s kind=%s: %r", row.id, row.kind, exc)
            await self._store.mark_failed(row.id, f"render: {exc!r}", permanent=True)
            return False

        try:
            await self._sender.send_message(row.chat_id, rendered.text, reply_markup=rendered.markup)
        except TelegramRetryAfter as exc:
            log.warning("outbox rate-limited id=%s retry_after=%s", row.id, exc.retry_after)
            await self._store.mark_failed(row.id, f"retry_after={exc.retry_after}")
            return False
        except (TelegramForbiddenError, TelegramBadRequest) as exc:
            # user blocked the bot / chat not found: retrying will not help
            log.warning("outbox permanent failure id=%s kind=%s: %s", row.id, row.kind, exc)
            await self._store.mark_failed(row.id, repr(exc), permanent=True)
            return False
        except Exception as exc:
            log.exception("outbox send failed id=%s kind=%s", row.id, row.kind)
            await self._store.mark_failed(row.id, repr(exc))
            return False

        await self._store.mark_sent(row.id)
        log.info("outbox sent id=%s kind=%s", row.id, row.kind)
        await self._send_extras(row, rendered.extras)
        return True

    async def _send_extras(self, row: Notification, extras: list[dict[str, Any]]) -> None:
        """Files after the text are best-effort: the text already went out."""
        if not extras:
            return
        if self._archive is None:
            log.warning("outbox id=%s has %s files but no archive sender", row.id, len(extras))
            return
        for attachment in extras:
            try:
                await self._archive.send_to(row.chat_id, attachment)
            except TelegramAPIError as exc:
                log.warning("outbox id=%s could not send a file: %s", row.id, exc)
