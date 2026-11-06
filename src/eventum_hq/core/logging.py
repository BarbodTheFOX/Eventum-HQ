"""Logging: key=value lines to stdout and to a rotating file in ``data/logs/``."""

from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FORMAT = "%(asctime)s level=%(levelname)s logger=%(name)s msg=%(message)s"
MAX_BYTES = 10 * 1024 * 1024  # 10 MB per file
BACKUP_COUNT = 6  # 1 active + 6 rotated = 7 files

# Telegram bot tokens look like 123456789:AA... — never let one reach the logs.
_TOKEN_RE = re.compile(r"\d{6,12}:[A-Za-z0-9_-]{30,}")


class RedactSecretsFilter(logging.Filter):
    def __init__(self, secrets: list[str] | None = None) -> None:
        super().__init__()
        self._secrets = [s for s in (secrets or []) if s]

    def redact(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, "***")
        return _TOKEN_RE.sub("***", text)

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = self.redact(message)
        if redacted != message:
            record.msg = redacted
            record.args = None
        return True


def setup_logging(level: str, log_dir: Path, secrets: list[str] | None = None) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(LOG_FORMAT)
    redactor = RedactSecretsFilter(secrets)

    stream = logging.StreamHandler(sys.stdout)
    file_handler = RotatingFileHandler(
        log_dir / "eventum.log", maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    for handler in (stream, file_handler):
        handler.setFormatter(formatter)
        handler.addFilter(redactor)
        root.addHandler(handler)
    root.setLevel(level)
    # aiohttp access/debug noise is not useful for a polling bot.
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
