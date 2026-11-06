from __future__ import annotations

import pytest

from eventum_hq.core.config import DEFAULT_DATABASE_URL, load_settings
from eventum_hq.core.errors import ConfigError

ENV_KEYS = [
    "BOT_TOKEN",
    "OWNER_TELEGRAM_ID",
    "TEAM_GROUP_ID",
    "ARCHIVE_CHANNEL_ID",
    "DATABASE_URL",
    "TELEGRAM_PROXY",
    "LOG_LEVEL",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_missing_owner_id_gives_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "123:abc")
    with pytest.raises(ConfigError) as info:
        load_settings(_env_file=None)
    assert "OWNER_TELEGRAM_ID" in str(info.value)


def test_empty_owner_id_counts_as_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "123:abc")
    monkeypatch.setenv("OWNER_TELEGRAM_ID", "")
    with pytest.raises(ConfigError, match="OWNER_TELEGRAM_ID"):
        load_settings(_env_file=None)


def test_missing_token_gives_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OWNER_TELEGRAM_ID", "42")
    with pytest.raises(ConfigError, match="BOT_TOKEN"):
        load_settings(_env_file=None)


def test_minimal_config_and_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "123:abc")
    monkeypatch.setenv("OWNER_TELEGRAM_ID", "42")
    monkeypatch.setenv("TEAM_GROUP_ID", "")
    monkeypatch.setenv("TELEGRAM_PROXY", "")
    s = load_settings(_env_file=None)
    assert s.owner_telegram_id == 42
    assert s.team_group_id is None
    assert s.archive_channel_id is None
    assert s.telegram_proxy is None
    assert s.database_url == DEFAULT_DATABASE_URL
    assert s.log_level == "INFO"
    assert "123:abc" not in repr(s)  # token is a SecretStr


def test_proxy_and_group_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "123:abc")
    monkeypatch.setenv("OWNER_TELEGRAM_ID", "42")
    monkeypatch.setenv("TEAM_GROUP_ID", "-1001234567890")
    monkeypatch.setenv("TELEGRAM_PROXY", "socks5://127.0.0.1:10808")
    s = load_settings(_env_file=None)
    assert s.team_group_id == -1001234567890
    assert s.telegram_proxy == "socks5://127.0.0.1:10808"


def test_invalid_proxy_scheme_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "123:abc")
    monkeypatch.setenv("OWNER_TELEGRAM_ID", "42")
    monkeypatch.setenv("TELEGRAM_PROXY", "127.0.0.1:10808")
    with pytest.raises(ConfigError, match="TELEGRAM_PROXY"):
        load_settings(_env_file=None)


def test_env_file_with_inline_comment(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "BOT_TOKEN=123:abc\nOWNER_TELEGRAM_ID=42\nTELEGRAM_PROXY=   # local only\n",
        encoding="utf-8",
    )
    s = load_settings(_env_file=env)
    assert s.telegram_proxy is None
