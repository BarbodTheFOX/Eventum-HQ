"""Application configuration loaded from environment variables / ``.env``."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from eventum_hq.core.errors import ConfigError

DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///data/eventum.db"

_COMMON_CONFIG = SettingsConfigDict(
    env_file=".env",
    env_file_encoding="utf-8",
    env_ignore_empty=True,  # "KEY=" in .env means "not set"
    extra="ignore",
)


class DatabaseSettings(BaseSettings):
    """Only what Alembic needs (so migrations work without a bot token)."""

    model_config = _COMMON_CONFIG

    database_url: str = DEFAULT_DATABASE_URL


class Settings(DatabaseSettings):
    model_config = _COMMON_CONFIG

    bot_token: SecretStr
    owner_telegram_id: int
    team_group_id: int | None = None
    archive_channel_id: int | None = None
    telegram_proxy: str | None = None
    log_level: str = "INFO"
    log_dir: Path = Field(default=Path("data/logs"))

    @field_validator("telegram_proxy")
    @classmethod
    def _check_proxy(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        allowed = ("socks5://", "socks4://", "http://", "https://")
        if not value.lower().startswith(allowed):
            raise ValueError(
                "TELEGRAM_PROXY must start with socks5://, socks4://, http:// or https://"
            )
        return value

    @field_validator("log_level")
    @classmethod
    def _check_log_level(cls, value: str) -> str:
        value = value.strip().upper()
        if value not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR or CRITICAL")
        return value


_FIELD_HELP = {
    "bot_token": "BOT_TOKEN is not set. Put the TEST bot token (from @BotFather) in .env.",
    "owner_telegram_id": (
        "OWNER_TELEGRAM_ID is not set or is not a number. Put the owner's numeric "
        "Telegram ID in .env (you can get it from @userinfobot)."
    ),
}


def load_settings(**overrides: object) -> Settings:
    """Load settings, turning validation errors into one clear ``ConfigError``."""
    try:
        return Settings(**overrides)  # type: ignore[arg-type]
    except ValidationError as exc:
        lines = ["Configuration error — the bot cannot start:"]
        for err in exc.errors():
            field = str(err["loc"][0]) if err["loc"] else "?"
            default_help = f"{field.upper()}: {err['msg']}"
            lines.append(f"  - {_FIELD_HELP.get(field, default_help)}")
        raise ConfigError("\n".join(lines)) from None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
