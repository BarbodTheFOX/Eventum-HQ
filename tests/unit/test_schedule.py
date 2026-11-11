"""Quiet hours, Tehran wall clock and retry backoff (M5)."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from eventum_hq.core.jalali import tehran_to_utc
from eventum_hq.services import schedule
from eventum_hq.services.notifications import backoff

Q_START, Q_END = time(23, 0), time(9, 0)


def _tehran(hh: int, mm: int = 0, day: date = date(2026, 11, 7)) -> datetime:
    return tehran_to_utc(day, time(hh, mm))


def test_quiet_window_crosses_midnight() -> None:
    assert schedule.in_quiet_hours(_tehran(23, 0), Q_START, Q_END)
    assert schedule.in_quiet_hours(_tehran(2, 30), Q_START, Q_END)
    assert schedule.in_quiet_hours(_tehran(8, 59), Q_START, Q_END)
    assert not schedule.in_quiet_hours(_tehran(9, 0), Q_START, Q_END)
    assert not schedule.in_quiet_hours(_tehran(22, 59), Q_START, Q_END)


def test_quiet_window_same_day() -> None:
    assert schedule.in_quiet_hours(_tehran(13, 0), time(12, 0), time(14, 0))
    assert not schedule.in_quiet_hours(_tehran(14, 0), time(12, 0), time(14, 0))


def test_quiet_end_after() -> None:
    assert schedule.quiet_end_after(_tehran(23, 30), Q_END) == _tehran(9, 0, date(2026, 11, 8))
    assert schedule.quiet_end_after(_tehran(3, 0), Q_END) == _tehran(9, 0)


def test_week_starts_on_saturday() -> None:
    wednesday = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
    assert schedule.week_start(wednesday) == date(2026, 11, 7)  # a Saturday
    assert schedule.week_start(_tehran(0, 5)) == date(2026, 11, 7)


def test_is_due_today() -> None:
    saturday_morning = _tehran(9, 0)
    assert schedule.is_due_today(saturday_morning, 0, time(9, 0))
    assert not schedule.is_due_today(saturday_morning, 0, time(9, 1))
    assert not schedule.is_due_today(saturday_morning, 1, time(8, 0))


def test_backoff_doubles_and_caps() -> None:
    assert [backoff(n) for n in (1, 2, 3, 4)] == [timedelta(minutes=m) for m in (1, 2, 4, 8)]
    assert backoff(10) == timedelta(minutes=30)
