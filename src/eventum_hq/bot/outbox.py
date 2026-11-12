"""Delivers outbox rows written by services.

Urgent rows are delivered right after each update (``OutboxFlushMiddleware``)
and once at startup; the 60-second tick (M5) delivers every due row. Quiet hours
and retry backoff are decided by :class:`OutboxStore`.

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
from aiogram.types import FSInputFile, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove

from eventum_hq.bot import texts
from eventum_hq.bot.formatters import (
    access_request_card,
    daily_plan_text,
    esc,
    fa_digits,
    format_jalali_date,
    format_jalali_datetime,
    overdue_daily_text,
    reel_card,
    review_card,
    role_label,
    saturday_report_text,
    task_card,
    weekly_summary_text,
)
from eventum_hq.bot.keyboards.access import access_request_keyboard
from eventum_hq.bot.keyboards.main_menu import main_menu
from eventum_hq.bot.keyboards.reels import reel_card_keyboard
from eventum_hq.bot.keyboards.tasks import review_keyboard, review_queue_keyboard, task_card_keyboard
from eventum_hq.core.timeutil import Clock, to_tehran
from eventum_hq.integrations.telegram_archive import TelegramArchive
from eventum_hq.models import Notification, TaskKind, TaskStatus
from eventum_hq.services import deadlines as deadline_kinds
from eventum_hq.services import periodic as periodic_kinds
from eventum_hq.services import delegations as delegation_kinds
from eventum_hq.services import offboarding as offboarding_kinds
from eventum_hq.services import system as system_kinds
from eventum_hq.services import reels as reel_kinds
from eventum_hq.services import reviews as review_kinds
from eventum_hq.services import tasks as task_kinds
from eventum_hq.services import users as user_kinds
from eventum_hq.services.deadlines import DeadlineService
from eventum_hq.services.notifications import OutboxStore
from eventum_hq.services.reels import ReelService
from eventum_hq.services.reports import ReportService
from eventum_hq.services.reviews import ReviewService
from eventum_hq.services.tasks import TaskRow, TaskService
from eventum_hq.services.users import UserService

log = logging.getLogger(__name__)

Markup = InlineKeyboardMarkup | ReplyKeyboardMarkup | ReplyKeyboardRemove | None
MAX_TEXT = 4000  # Telegram's limit is 4096 characters per message


class MessageSender(Protocol):
    async def send_message(self, chat_id: int, text: str, **kwargs: Any) -> Any: ...

    async def send_document(self, chat_id: int, document: Any, **kwargs: Any) -> Any: ...


class UnknownNotificationKind(Exception):
    pass


class UndeliverableNotification(Exception):
    """The notification no longer makes sense (e.g. recipient lost access)."""


@dataclass(slots=True)
class Rendered:
    text: str
    markup: Markup = None
    extras: list[dict[str, Any]] = field(default_factory=list)  # attachments sent after the text
    document: str | None = None  # local file sent instead of a text (weekly backup); text = caption


@dataclass(slots=True)
class RenderContext:
    users: UserService
    tasks: TaskService | None = None
    reviews: ReviewService | None = None
    clock: Clock | None = None
    reels: ReelService | None = None
    deadlines: DeadlineService | None = None
    reports: ReportService | None = None

    def now(self) -> datetime:
        if self.clock is None:
            raise UnknownNotificationKind("no clock")
        return self.clock.now()


_TASK_CARD_KINDS = {task_kinds.KIND_TASK_ASSIGNED, task_kinds.KIND_TASK_DUE_CHANGED}
_DEADLINE_PREFIX = {
    deadline_kinds.KIND_REMINDER_DAY: texts.NOTIFY_REMINDER_DAY,
    deadline_kinds.KIND_REMINDER_SOON: texts.NOTIFY_REMINDER_SOON,
    deadline_kinds.KIND_OVERDUE: texts.NOTIFY_OVERDUE,
}
_STILL_PENDING = (TaskStatus.TODO, TaskStatus.IN_PROGRESS)


def split_text(text: str, limit: int = MAX_TEXT) -> list[str]:
    """Split a long message at line breaks so every part fits in one Telegram message."""
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    current = ""
    for line in text.split("\n"):
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit and current:
            parts.append(current)
            current = line[:limit]
        else:
            current = candidate[:limit]
    if current:
        parts.append(current)
    return parts


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

    # ---- deadlines (M5)
    if kind in _DEADLINE_PREFIX:
        if ctx.tasks is None:
            raise UnknownNotificationKind("no task service")
        recipient = await _recipient(ctx, payload)
        view = await ctx.tasks.get_view(recipient, task_id=int(payload["task_id"]))
        task = view.task
        if task.status not in _STILL_PENDING or task.first_submitted_at is not None or task.due_at is None:
            raise UndeliverableNotification("task no longer pending")
        if kind != deadline_kinds.KIND_OVERDUE and task.due_at <= ctx.now():
            raise UndeliverableNotification("reminder is too late")  # e.g. held back by quiet hours
        prefix = _DEADLINE_PREFIX[kind].format(code=esc(task.code))
        return Rendered(prefix + task_card(view, ctx.now()), task_card_keyboard(view))
    if kind == deadline_kinds.KIND_OVERDUE_WATCH:
        return Rendered(texts.NOTIFY_OVERDUE_WATCH.format(code=code, title=title,
                                                          assignee=esc(payload.get("assignee") or "")))
    if kind == deadline_kinds.KIND_OVERDUE_DAILY:
        if ctx.deadlines is None:
            raise UnknownNotificationKind("no deadline service")
        recipient = await _recipient(ctx, payload)
        scope = str(payload.get("scope") or deadline_kinds.SCOPE_MINE)
        rows = await ctx.deadlines.overdue_for(recipient, scope)
        if not rows:
            raise UndeliverableNotification("nothing overdue any more")
        return Rendered(overdue_daily_text(rows, scope, ctx.now()))

    # ---- reports and group messages (M5)
    if kind == periodic_kinds.KIND_SATURDAY_REPORT:
        if ctx.reports is None:
            raise UnknownNotificationKind("no report service")
        recipient = await _recipient(ctx, payload)
        return report_message(await ctx.reports.saturday(recipient), ctx.now())
    if kind == periodic_kinds.KIND_DAILY_PLAN:
        if ctx.reports is None:
            raise UnknownNotificationKind("no report service")
        plan = await ctx.reports.daily_plan()
        if plan.empty:
            raise UndeliverableNotification("nothing planned today")
        return Rendered(daily_plan_text(plan))
    if kind == periodic_kinds.KIND_WEEKLY_SUMMARY:
        if ctx.reports is None:
            raise UnknownNotificationKind("no report service")
        return Rendered(weekly_summary_text(await ctx.reports.weekly_summary()))

    # ---- system (M5)
    if kind == periodic_kinds.KIND_HEARTBEAT:
        since = format_jalali_datetime(datetime.fromisoformat(payload["since"]))
        return Rendered(texts.HEARTBEAT_ALERT.format(minutes=fa_digits(payload.get("minutes", 0)), since=since))
    if kind == periodic_kinds.KIND_BACKUP_WEEKLY:
        caption = texts.BACKUP_WEEKLY_CAPTION.format(date=format_jalali_date(to_tehran(ctx.now()).date()))
        return Rendered(caption, document=str(payload["path"]))
    if kind == system_kinds.KIND_SYSTEM_ERROR:
        return Rendered(texts.NOTIFY_SYSTEM_ERROR.format(error=esc(payload.get("error", "")),
                                                         where=esc(payload.get("where", "")),
                                                         message=esc(payload.get("message", ""))))
    if kind == offboarding_kinds.KIND_USER_DEACTIVATED:
        text = texts.NOTIFY_USER_DEACTIVATED.format(
            name=esc(payload.get("name") or ""), role=role_label(payload.get("role")),
            actor=esc(payload.get("actor_name") or ""), open=fa_digits(payload.get("open_tasks", 0)),
            recs=fa_digits(payload.get("recurrences", 0)),
        )
        missing = payload.get("missing") or []
        if missing:
            text += texts.NOTIFY_USER_DEACTIVATED_CAPS.format(
                caps="\n".join(f"• {texts.CAPABILITY_LABELS.get(c, esc(c))}" for c in missing))
        return Rendered(text)
    if kind == periodic_kinds.KIND_BACKUP_TOO_BIG:
        size_mb = round(int(payload.get("size", 0)) / (1024 * 1024), 1)
        return Rendered(texts.BACKUP_TOO_BIG.format(size=fa_digits(size_mb), path=esc(payload.get("path", ""))))

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

    # ---- reels
    if kind == reel_kinds.KIND_REEL_PHOTOS_READY:
        if ctx.tasks is None:
            raise UnknownNotificationKind("no task service")
        recipient = await _recipient(ctx, payload)
        view = await ctx.tasks.get_view(recipient, task_id=int(payload["task_id"]))
        photos = [a for i in view.inputs if str(i.kind) == "COVER_PHOTOS" for a in i.attachments]
        prefix = texts.NOTIFY_REEL_PHOTOS_READY.format(reel_code=esc(payload.get("reel_code", "")))
        return Rendered(prefix + task_card(view, ctx.now()), task_card_keyboard(view), photos)
    if kind == reel_kinds.KIND_REEL_TASK_APPROVED:
        return Rendered(texts.NOTIFY_REEL_TASK_APPROVED.format(
            kind=texts.REEL_TASK_KIND_LABELS.get(payload.get("task_kind", ""), ""),
            reel_code=esc(payload.get("reel_code", "")), title=title))
    if kind == reel_kinds.KIND_REEL_CANCELLED:
        return Rendered(texts.NOTIFY_REEL_CANCELLED.format(reel_code=esc(payload.get("reel_code", "")), title=title))
    if kind in (reel_kinds.KIND_REEL_READY, reel_kinds.KIND_REEL_PUBLISHED):
        if ctx.reels is None:
            raise UnknownNotificationKind("no reel service")
        recipient = await _recipient(ctx, payload)
        view = await ctx.reels.view(recipient, item_id=int(payload["content_item_id"]))
        if kind == reel_kinds.KIND_REEL_READY:
            prefix = texts.NOTIFY_REEL_READY.format(reel_code=esc(view.item.code))
            files = await ctx.reels.final_files(view.item.id)
        else:
            prefix = texts.NOTIFY_REEL_PUBLISHED.format(reel_code=esc(view.item.code))
            files = []
        return Rendered(prefix + reel_card(view), reel_card_keyboard(view), files)

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


def report_message(report: Any, now: datetime) -> Rendered:
    """Saturday report text + one button per task waiting for my approval."""
    rows = [TaskRow(line.task, line.assignee) for line in report.approvals]
    markup = review_queue_keyboard(rows, now) if rows else None
    return Rendered(saturday_report_text(report, now), markup)


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
        reels: ReelService | None = None,
        deadlines: DeadlineService | None = None,
        reports: ReportService | None = None,
    ) -> None:
        self._sender = sender
        self._store = store
        self._ctx = RenderContext(users=users, tasks=tasks, reviews=reviews, clock=clock, reels=reels,
                                  deadlines=deadlines, reports=reports)
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

    async def deliver_due(self) -> int:
        """Send every due row, urgent or not (the 60-second tick). Returns the number sent."""
        sent = 0
        async with self._lock:
            for row in await self._store.due_all():
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
            if rendered.document is not None:
                await self._sender.send_document(row.chat_id, FSInputFile(rendered.document),
                                                 caption=rendered.text)
            else:
                parts = split_text(rendered.text)
                for i, part in enumerate(parts):
                    markup = rendered.markup if i == len(parts) - 1 else None
                    await self._sender.send_message(row.chat_id, part, reply_markup=markup)
        except TelegramRetryAfter as exc:
            log.warning("outbox rate-limited id=%s retry_after=%s", row.id, exc.retry_after)
            await self._store.mark_failed(row.id, f"retry_after={exc.retry_after}", retry_after=exc.retry_after)
            return False
        except FileNotFoundError as exc:
            log.warning("outbox file missing id=%s: %s", row.id, exc)
            await self._store.mark_failed(row.id, repr(exc), permanent=True)
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
