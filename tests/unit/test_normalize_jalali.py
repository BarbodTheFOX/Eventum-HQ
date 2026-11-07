"""Jalali input and Persian normalization (handoff §4.9, §5.3, §10)."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pytest

from eventum_hq.core.jalali import (
    InvalidDateInput,
    InvalidTimeInput,
    QuickDate,
    jalali_parts,
    parse_date_input,
    parse_time_input,
    quick_date,
    tehran_to_utc,
    tehran_today,
)
from eventum_hq.core.normalize import normalize_digits, normalize_text

TODAY = date(2026, 11, 7)  # = 1405/08/16, a Saturday


# ---- normalize ----------------------------------------------------------------


def test_digits() -> None:
    assert normalize_digits("۱۴۰۵/۸/۲۰") == "1405/8/20"
    assert normalize_digits("٠١٢٣٤٥٦٧٨٩") == "0123456789"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("علي", "علی"),
        ("كاور", "کاور"),
        ("می‌شود", "میشود"),  # ZWNJ removed
        ("مُحَمَّد", "محمد"),  # diacritics removed
        ("  Purple   ZONE ", "purple zone"),
        ("ریل ۱۲", "ریل 12"),
        ("كتابخانهٔ", "کتابخانه"),  # hamza-above is a diacritic too
    ],
)
def test_normalize_text(raw: str, expected: str) -> None:
    assert normalize_text(raw) == expected


# ---- date input ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected_date", "expected_time"),
    [
        ("1405/08/20", date(2026, 11, 11), None),
        ("۱۴۰۵/۸/۲۰", date(2026, 11, 11), None),
        ("1405/08/20 18:30", date(2026, 11, 11), time(18, 30)),
        ("۱۴۰۵/۰۸/۲۰ ۱۸:۳۰", date(2026, 11, 11), time(18, 30)),
        ("08/20", date(2026, 11, 11), None),  # year defaults to current Jalali year
        ("8/20 9", date(2026, 11, 11), time(9, 0)),
        ("1405-08-20", date(2026, 11, 11), None),
        ("٨/٢٠", date(2026, 11, 11), None),  # Arabic digits
        ("1405/12/29", date(2027, 3, 20), None),
    ],
)
def test_parse_date_input(text: str, expected_date: date, expected_time: time | None) -> None:
    parsed = parse_date_input(text, TODAY)
    assert parsed.date == expected_date
    assert parsed.time == expected_time


@pytest.mark.parametrize(
    "text",
    ["", "فردا", "1405/13/01", "1405/07/31", "1405/08/20 25:00", "1405/08/20 18:61", "20", "abc/de"],
)
def test_parse_date_input_rejects_invalid(text: str) -> None:
    with pytest.raises(InvalidDateInput):
        parse_date_input(text, TODAY)


@pytest.mark.parametrize(
    ("text", "expected"),
    [("18:30", time(18, 30)), ("۱۸:۳۰", time(18, 30)), ("9", time(9, 0)), ("0:05", time(0, 5))],
)
def test_parse_time_input(text: str, expected: time) -> None:
    assert parse_time_input(text) == expected


@pytest.mark.parametrize("text", ["24:00", "12:60", "ساعت", "", "18.30"])
def test_parse_time_input_rejects_invalid(text: str) -> None:
    with pytest.raises(InvalidTimeInput):
        parse_time_input(text)


@pytest.mark.parametrize(
    ("key", "today", "expected"),
    [
        (QuickDate.TODAY, TODAY, TODAY),
        (QuickDate.TOMORROW, TODAY, date(2026, 11, 8)),
        (QuickDate.AFTER_TOMORROW, TODAY, date(2026, 11, 9)),
        (QuickDate.NEXT_SATURDAY, TODAY, date(2026, 11, 14)),  # today is Saturday → +7
        (QuickDate.NEXT_SATURDAY, date(2026, 11, 13), date(2026, 11, 14)),  # Friday → +1
        (QuickDate.NEXT_SATURDAY, date(2026, 11, 10), date(2026, 11, 14)),  # Tuesday
    ],
)
def test_quick_date(key: QuickDate, today: date, expected: date) -> None:
    assert quick_date(key, today) == expected


def test_tehran_conversions() -> None:
    utc = tehran_to_utc(date(2026, 11, 11), time(18, 0))
    assert utc == datetime(2026, 11, 11, 14, 30, tzinfo=UTC)  # Tehran = UTC+3:30
    # 22:00 UTC is already the next day in Tehran
    assert tehran_today(datetime(2026, 11, 7, 22, 0, tzinfo=UTC)) == date(2026, 11, 8)
    parts = jalali_parts(utc)
    assert (parts.year, parts.month, parts.day, parts.hour, parts.minute) == (1405, 8, 20, 18, 0)
    assert parts.weekday == 4  # Wednesday (Saturday = 0)


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (timedelta(minutes=45), "۴۵ دقیقه مانده"),
        (timedelta(seconds=20), "۱ دقیقه مانده"),
        (timedelta(hours=3, minutes=10), "۳ ساعت مانده"),
        (timedelta(days=2, hours=5), "۲ روز مانده"),
        (-timedelta(hours=26), "۱ روز تأخیر"),
        (-timedelta(minutes=5), "۵ دقیقه تأخیر"),
    ],
)
def test_humanize_delta(delta: timedelta, expected: str) -> None:
    from eventum_hq.bot.formatters import humanize_delta

    now = datetime(2026, 11, 7, 8, 0, tzinfo=UTC)
    assert humanize_delta(now + delta, now) == expected


def test_format_jalali_datetime() -> None:
    from eventum_hq.bot.formatters import format_jalali_datetime

    assert format_jalali_datetime(datetime(2026, 11, 11, 15, 0, tzinfo=UTC)) == "چهارشنبه ۱۴۰۵/۰۸/۲۰ ساعت ۱۸:۳۰"
