"""Small helpers that turn domain values into display strings (HTML-escaped)."""

from __future__ import annotations

from datetime import date, datetime
from html import escape

from eventum_hq.bot import texts
from eventum_hq.core.jalali import jalali_date_parts, jalali_parts
from eventum_hq.models import Role, Task, TaskStatus, User
from eventum_hq.services.reviews import ReviewView
from eventum_hq.services.tasks import (
    DeadlineState,
    HistoryEntry,
    TaskRow,
    TaskView,
    deadline_state,
)


def esc(value: object) -> str:
    return escape(str(value), quote=False)


def display_name(full_name: str | None) -> str:
    name = (full_name or "").strip()
    return esc(name) if name else texts.NO_NAME


def display_username(username: str | None) -> str:
    return f"@{esc(username)}" if username else texts.NO_USERNAME


def role_label(role: Role | str | None) -> str:
    try:
        return texts.ROLE_LABELS[Role(role)] if role is not None else "—"
    except ValueError:
        return esc(role)


def access_request_card(
    *, full_name: str | None, username: str | None, telegram_id: int, role: Role | str | None
) -> str:
    return texts.ACCESS_REQUEST_CARD.format(
        name=display_name(full_name),
        username=display_username(username),
        telegram_id=int(telegram_id),
        role=role_label(role),
    )


# ---- digits, dates, deltas ----------------------------------------------------

_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def fa_digits(value: object) -> str:
    return str(value).translate(_FA_DIGITS)


def format_jalali_datetime(value: datetime) -> str:
    p = jalali_parts(value)
    text = texts.DATETIME_FORMAT.format(
        weekday=texts.WEEKDAYS[p.weekday], y=p.year, m=p.month, d=p.day, hh=p.hour, mm=p.minute
    )
    return fa_digits(text)


def format_jalali_date(day: date) -> str:
    y, m, d, weekday = jalali_date_parts(day)
    return fa_digits(texts.DATE_FORMAT.format(weekday=texts.WEEKDAYS[weekday], y=y, m=m, d=d))


def humanize_delta(due: datetime, now: datetime) -> str:
    """'۳ ساعت مانده' / '۱ روز تأخیر' / '۴۵ دقیقه مانده'."""
    seconds = (due - now).total_seconds()
    template = texts.DELTA_LEFT if seconds >= 0 else texts.DELTA_LATE
    minutes = int(abs(seconds) // 60)
    if minutes < 60:
        n, unit = max(minutes, 1), texts.UNIT_MINUTE
    elif minutes < 24 * 60:
        n, unit = minutes // 60, texts.UNIT_HOUR
    else:
        n, unit = minutes // (24 * 60), texts.UNIT_DAY
    return template.format(n=fa_digits(n), unit=unit)


def format_minutes(minutes: int | None) -> str:
    """90 → '۱ ساعت و ۳۰ دقیقه'; None → '—'."""
    if not minutes:
        return texts.NO_ESTIMATE
    hours, rest = divmod(int(minutes), 60)
    if hours == 0:
        return fa_digits(texts.DURATION_MINUTES.format(m=rest))
    if rest == 0:
        return fa_digits(texts.DURATION_HOURS.format(h=hours))
    return fa_digits(texts.DURATION_HOURS_MINUTES.format(h=hours, m=rest))


def user_label(user: User | None, *, with_role: bool = False, html: bool = True) -> str:
    """Display name. ``html=False`` for button labels (buttons show text literally)."""
    if user is None:
        return texts.SYSTEM_ACTOR
    clean = esc if html else str
    if (user.full_name or "").strip():
        name = clean(user.full_name.strip())
    elif user.username:
        name = f"@{clean(user.username)}"
    else:
        name = fa_digits(user.telegram_id)
    return f"{name} ({role_label(user.role)})" if with_role else name


# ---- tasks -----------------------------------------------------------------------


def deadline_emoji(task: Task, now: datetime) -> str:
    state = deadline_state(task, now)
    if state == DeadlineState.OVERDUE:
        return texts.OVERDUE_EMOJI
    if state == DeadlineState.AT_RISK:
        return texts.AT_RISK_EMOJI
    return ""


def format_due(task: Task, now: datetime) -> str:
    if task.due_at is None:
        return texts.NO_DEADLINE
    due = format_jalali_datetime(task.due_at)
    if deadline_state(task, now) == DeadlineState.NONE:
        return due
    emoji = deadline_emoji(task, now)
    return texts.DUE_WITH_DELTA.format(
        due=due, emoji=f"{emoji} " if emoji else "", delta=humanize_delta(task.due_at, now)
    )


def task_card(view: TaskView, now: datetime) -> str:
    t = view.task
    text = texts.TASK_CARD.format(
        code=esc(t.code),
        title=esc(t.title),
        status=status_label(t),
        assignee=user_label(view.assignee),
        due=format_due(t, now),
        series=esc(view.series.name) if view.series else texts.NO_SERIES,
        chain=texts.CHAIN_LABELS[t.approval_chain],
        estimate=format_minutes(t.estimated_minutes),
        rounds=fa_digits(t.revision_round),
        creator=user_label(view.creator),
    )
    if t.description:
        text += texts.TASK_CARD_DESCRIPTION.format(description=esc(t.description))
    if view.brief is not None and view.brief.attachments:
        text += texts.TASK_CARD_BRIEF.format(count=fa_digits(len(view.brief.attachments)))
    if view.latest_version:
        text += texts.TASK_CARD_VERSION.format(version=fa_digits(view.latest_version))
    if view.last_event is not None:
        text += texts.TASK_CARD_LAST_EVENT.format(
            event=texts.AUDIT_LABELS.get(view.last_event.action, esc(view.last_event.action)),
            actor=user_label(view.last_actor),
            when=format_jalali_datetime(view.last_event.at),
        )
    return text


def status_label(task: Task) -> str:
    label = texts.STATUS_LABELS[task.status]
    if task.status == TaskStatus.IN_REVIEW and task.review_stage is not None:
        return texts.STATUS_WITH_STAGE.format(status=label, stage=texts.STAGE_LABELS[str(task.review_stage)])
    return label


def review_card(view: ReviewView, now: datetime) -> str:
    t, sub = view.task, view.submission
    text = texts.REVIEW_CARD.format(
        code=esc(t.code),
        title=esc(t.title),
        assignee=user_label(view.assignee),
        version=fa_digits(sub.version),
        rounds=fa_digits(t.revision_round),
        stage=texts.STAGE_LABELS[str(view.stage)],
        due=format_due(t, now),
        series=esc(view.series.name) if view.series else texts.NO_SERIES,
    )
    if sub.note:
        text += texts.REVIEW_CARD_NOTE.format(note=esc(sub.note))
    if sub.links:
        text += texts.REVIEW_CARD_LINKS.format(links="\n".join(esc(link) for link in sub.links))
    if sub.attachments:
        text += texts.REVIEW_CARD_FILES.format(count=fa_digits(len(sub.attachments)))
    return text


def task_list_text(header: str, rows: list[TaskRow], now: datetime) -> str:
    if not rows:
        return header + texts.LIST_EMPTY
    lines = []
    for row in rows:
        t = row.task
        state = deadline_state(t, now)
        delta = (
            texts.LIST_LINE_DELTA.format(delta=humanize_delta(t.due_at, now))
            if t.due_at is not None and state != DeadlineState.NONE
            else ""
        )
        lines.append(
            texts.LIST_LINE.format(
                emoji=deadline_emoji(t, now) or texts.STATUS_EMOJI[t.status],
                code=esc(t.code),
                title=esc(_short(t.title, 40)),
                assignee=user_label(row.assignee),
                delta=delta,
            )
        )
    return header + "".join(lines)


def task_button_label(task: Task, now: datetime) -> str:
    emoji = deadline_emoji(task, now) or texts.STATUS_EMOJI[task.status]
    return f"{emoji} {task.code} · {_short(task.title, 28)}"


def history_text(task: Task, entries: list[HistoryEntry]) -> str:
    text = texts.HISTORY_HEADER.format(code=esc(task.code))
    for entry in entries:
        text += texts.HISTORY_LINE.format(
            when=format_jalali_datetime(entry.event.at),
            label=texts.AUDIT_LABELS.get(entry.event.action, esc(entry.event.action)),
            actor=user_label(entry.actor),
        )
    return text


def _short(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
