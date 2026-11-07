"""Jalali (Shamsi) date input parsing and conversion. No UI text here.

Accepted manual input (handoff §5.3), Persian/Arabic digits allowed:
    1405/08/20      ۱۴۰۵/۸/۲۰      1405/08/20 18:30      08/20      8/20 18:30
The year is optional (default: current Jalali year in Tehran). ``-`` works as ``/``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum

import jdatetime

from eventum_hq.core.errors import DomainError
from eventum_hq.core.normalize import normalize_digits
from eventum_hq.core.timeutil import TEHRAN, to_tehran


class InvalidDateInput(DomainError):
    """The text is not a valid Jalali date/time."""


class InvalidTimeInput(DomainError):
    """The text is not a valid HH:MM time."""


@dataclass(frozen=True, slots=True)
class ParsedDate:
    date: date  # Gregorian date (Tehran calendar day)
    time: time | None


_DATE_RE = re.compile(
    r"^(?:(?P<y>\d{4})/)?(?P<m>\d{1,2})/(?P<d>\d{1,2})"
    r"(?:\s+(?P<hh>\d{1,2})(?::(?P<mm>\d{1,2}))?)?$"
)
_TIME_RE = re.compile(r"^(?P<hh>\d{1,2})(?::(?P<mm>\d{1,2}))?$")


def _clean(text: str) -> str:
    text = normalize_digits(text or "").strip()
    text = text.replace("-", "/").replace("\\", "/").replace("：", ":")
    return re.sub(r"\s+", " ", text)


def _make_time(hh: str | None, mm: str | None, error: type[DomainError]) -> time:
    hour = int(hh) if hh is not None else 0
    minute = int(mm) if mm is not None else 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise error(f"{hh}:{mm}")
    return time(hour, minute)


def parse_date_input(text: str, today: date) -> ParsedDate:
    """Parse a manual Jalali date (optionally with time). ``today`` = Tehran today."""
    match = _DATE_RE.match(_clean(text))
    if match is None:
        raise InvalidDateInput(text)
    year = int(match["y"]) if match["y"] else jdatetime.date.fromgregorian(date=today).year
    try:
        gregorian = jdatetime.date(year, int(match["m"]), int(match["d"])).togregorian()
    except ValueError as exc:
        raise InvalidDateInput(text) from exc
    parsed_time = (
        _make_time(match["hh"], match["mm"], InvalidDateInput) if match["hh"] is not None else None
    )
    return ParsedDate(gregorian, parsed_time)


def parse_time_input(text: str) -> time:
    match = _TIME_RE.match(_clean(text))
    if match is None:
        raise InvalidTimeInput(text)
    return _make_time(match["hh"], match["mm"], InvalidTimeInput)


class QuickDate(StrEnum):
    TODAY = "today"
    TOMORROW = "tomorrow"
    AFTER_TOMORROW = "after"
    NEXT_SATURDAY = "sat"


def quick_date(key: QuickDate | str, today: date) -> date:
    key = QuickDate(key)
    if key == QuickDate.TODAY:
        return today
    if key == QuickDate.TOMORROW:
        return today + timedelta(days=1)
    if key == QuickDate.AFTER_TOMORROW:
        return today + timedelta(days=2)
    # next Saturday strictly after today (Python: Monday=0 … Saturday=5)
    days = (5 - today.weekday()) % 7 or 7
    return today + timedelta(days=days)


def tehran_today(now_utc: datetime) -> date:
    return to_tehran(now_utc).date()


def tehran_to_utc(day: date, at: time) -> datetime:
    return datetime.combine(day, at, tzinfo=TEHRAN).astimezone(UTC)


@dataclass(frozen=True, slots=True)
class JalaliParts:
    year: int
    month: int
    day: int
    hour: int
    minute: int
    weekday: int  # Saturday = 0


def jalali_parts(value: datetime) -> JalaliParts:
    local = to_tehran(value)
    j = jdatetime.date.fromgregorian(date=local.date())
    return JalaliParts(j.year, j.month, j.day, local.hour, local.minute, (local.weekday() + 2) % 7)


def jalali_date_parts(day: date) -> tuple[int, int, int, int]:
    """(year, month, day, weekday Saturday=0) of a Gregorian calendar date."""
    j = jdatetime.date.fromgregorian(date=day)
    return j.year, j.month, j.day, (day.weekday() + 2) % 7


# ---- estimated time (F17) ---------------------------------------------------------


class InvalidEstimateInput(DomainError):
    """Not a valid duration like '90', '۱۴ ساعت', '1.5h', '45 دقیقه'."""


ESTIMATE_MAX_MINUTES = 200 * 60  # anything above ~200 hours is surely a typo

_ESTIMATE_RE = re.compile(
    r"^(?P<num>\d+(?:[.,]\d+)?)\s*(?P<unit>"
    r"h|hr|hrs|hour|hours|ساعت|m|min|mins|minute|minutes|دقیقه|)$",
    re.IGNORECASE,
)
_HOUR_UNITS = {"h", "hr", "hrs", "hour", "hours", "ساعت"}


def parse_estimate_input(text: str) -> int:
    """Return minutes. A bare number means minutes: '90' → 90, '1.5h' → 90, '۱۴ ساعت' → 840."""
    clean = normalize_digits(text or "").strip().lower().replace("٫", ".").replace("‌", "")
    clean = re.sub(r"\s+", " ", clean)
    match = _ESTIMATE_RE.match(clean)
    if match is None:
        raise InvalidEstimateInput(text)
    value = float(match["num"].replace(",", "."))
    minutes = round(value * 60) if match["unit"] in _HOUR_UNITS else round(value)
    if minutes <= 0 or minutes > ESTIMATE_MAX_MINUTES:
        raise InvalidEstimateInput(text)
    return minutes
