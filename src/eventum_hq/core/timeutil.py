"""Time helpers.

Rule: everything stored in the database is UTC. Display and input use the
Jalali calendar in ``Asia/Tehran``. Saturday is weekday 0.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from zoneinfo import ZoneInfo

TEHRAN = ZoneInfo("Asia/Tehran")


class Clock(Protocol):
    """Injectable source of the current time (always timezone-aware UTC)."""

    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


def utcnow() -> datetime:
    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    """Return ``value`` as an aware UTC datetime. Naive values are rejected."""
    if value.tzinfo is None:
        raise ValueError("naive datetime is not allowed; use an aware datetime")
    return value.astimezone(UTC)


def to_tehran(value: datetime) -> datetime:
    return ensure_utc(value).astimezone(TEHRAN)


def weekday_sat0(value: datetime) -> int:
    """Weekday in Tehran time where Saturday = 0 … Friday = 6."""
    return (to_tehran(value).weekday() + 2) % 7
