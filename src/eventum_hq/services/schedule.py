"""Schedule settings (handoff §7 seed) and Tehran wall-clock helpers for the M5 tick.

Values live in the ``settings`` table; the defaults below are used when a key
is missing (e.g. in tests that create tables without the seed migration).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from eventum_hq.core.jalali import tehran_to_utc, tehran_today
from eventum_hq.core.timeutil import to_tehran, weekday_sat0
from eventum_hq.models import Setting

DEFAULTS: dict[str, Any] = {
    "quiet_hours": ["23:00", "09:00"],
    "daily_digest": {"days": [0, 1, 2, 3, 4, 5], "time": "09:30"},
    "weekly_summary": {"day": 5, "time": "18:00"},
    "saturday_report_time": "09:00",
    "reminder_time": "10:00",
    "reminder_before_hours": 2,
    "owner_review_urgent_in_quiet_hours": False,
    "backup_daily_time": "04:00",
    "backup_weekly": {"day": 6, "time": "04:30"},  # Friday (Saturday = 0)
}


def parse_hhmm(value: str) -> time:
    hh, mm = str(value).strip().split(":")
    return time(int(hh), int(mm))


@dataclass(frozen=True, slots=True)
class ScheduleSettings:
    quiet_start: time
    quiet_end: time
    digest_days: frozenset[int]
    digest_time: time
    summary_day: int
    summary_time: time
    report_time: time
    reminder_time: time
    reminder_before: timedelta
    owner_review_urgent_in_quiet: bool
    backup_daily_time: time
    backup_weekly_day: int
    backup_weekly_time: time


async def load(session: AsyncSession) -> ScheduleSettings:
    values = dict(DEFAULTS)
    for key in DEFAULTS:
        row = await session.get(Setting, key)
        if row is not None and row.value is not None:
            values[key] = row.value
    quiet = values["quiet_hours"]
    digest = values["daily_digest"]
    summary = values["weekly_summary"]
    weekly_backup = values["backup_weekly"]
    return ScheduleSettings(
        quiet_start=parse_hhmm(quiet[0]),
        quiet_end=parse_hhmm(quiet[1]),
        digest_days=frozenset(int(d) for d in digest["days"]),
        digest_time=parse_hhmm(digest["time"]),
        summary_day=int(summary["day"]),
        summary_time=parse_hhmm(summary["time"]),
        report_time=parse_hhmm(values["saturday_report_time"]),
        reminder_time=parse_hhmm(values["reminder_time"]),
        reminder_before=timedelta(hours=float(values["reminder_before_hours"])),
        owner_review_urgent_in_quiet=bool(values["owner_review_urgent_in_quiet_hours"]),
        backup_daily_time=parse_hhmm(values["backup_daily_time"]),
        backup_weekly_day=int(weekly_backup["day"]),
        backup_weekly_time=parse_hhmm(weekly_backup["time"]),
    )


def in_quiet_hours(now: datetime, start: time, end: time) -> bool:
    """True inside [start, end) Tehran time; handles windows that cross midnight."""
    local = to_tehran(now).time()
    if start <= end:
        return start <= local < end
    return local >= start or local < end


def quiet_end_after(now: datetime, end: time) -> datetime:
    """The next moment the quiet window ends (UTC)."""
    today = tehran_today(now)
    candidate = tehran_to_utc(today, end)
    return candidate if candidate > now else tehran_to_utc(today + timedelta(days=1), end)


def today_at(now: datetime, at: time) -> datetime:
    """``at`` (Tehran wall clock) on today's Tehran date, as UTC."""
    return tehran_to_utc(tehran_today(now), at)


def start_of_today(now: datetime) -> datetime:
    return today_at(now, time(0, 0))


def week_start(now: datetime) -> date:
    """Saturday of the current Tehran week."""
    return tehran_today(now) - timedelta(days=weekday_sat0(now))


def local_date_key(now: datetime) -> str:
    return tehran_today(now).isoformat()


def is_due_today(now: datetime, weekday: int | None, at: time) -> bool:
    """True once ``at`` has passed today (and today is ``weekday`` when given)."""
    if weekday is not None and weekday_sat0(now) != weekday:
        return False
    return now >= today_at(now, at)


def tehran_time_of(value: datetime) -> time:
    return to_tehran(value).time()
