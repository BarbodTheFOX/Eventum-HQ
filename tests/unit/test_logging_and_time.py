from __future__ import annotations

import logging
from datetime import UTC, datetime

import pytest

from eventum_hq.core.logging import RedactSecretsFilter
from eventum_hq.core.timeutil import TEHRAN, ensure_utc, to_tehran, weekday_sat0


def _record(msg: str, *args: object) -> logging.LogRecord:
    return logging.LogRecord("t", logging.INFO, __file__, 1, msg, args, None)


def test_bot_token_is_redacted_from_logs() -> None:
    token = "1234567890:AAEhBP0av18yU3H8aDdG0QcQyJ8z1Wq9XbY"
    f = RedactSecretsFilter([token])
    rec = _record("GET https://api.telegram.org/bot%s/getMe", token)
    f.filter(rec)
    assert token not in rec.getMessage()
    assert "***" in rec.getMessage()


def test_token_pattern_redacted_even_if_not_listed() -> None:
    f = RedactSecretsFilter()
    rec = _record("token 987654321:ZZEhBP0av18yU3H8aDdG0QcQyJ8z1Wq9XbY leaked")
    f.filter(rec)
    assert "987654321:" not in rec.getMessage()


def test_tehran_conversion_and_saturday_is_zero() -> None:
    # 2026-11-07 is a Saturday. 21:00 UTC Friday = 00:30 Saturday in Tehran.
    friday_night_utc = datetime(2026, 11, 6, 21, 0, tzinfo=UTC)
    local = to_tehran(friday_night_utc)
    assert local.tzinfo == TEHRAN
    assert (local.hour, local.minute) == (0, 30)
    assert weekday_sat0(friday_night_utc) == 0
    assert weekday_sat0(datetime(2026, 11, 13, 9, 0, tzinfo=UTC)) == 6  # Friday


def test_naive_datetimes_are_rejected() -> None:
    with pytest.raises(ValueError):
        ensure_utc(datetime(2026, 1, 1))
