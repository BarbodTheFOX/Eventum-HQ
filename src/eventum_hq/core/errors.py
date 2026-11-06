"""Domain errors raised by services.

Services never format user-facing text. The bot layer maps each error class to a
Persian message in ``bot/texts.py``.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for all expected business-rule failures."""


class PermissionDenied(DomainError):
    """The actor is not allowed to perform this action."""


class NotFound(DomainError):
    """The requested entity does not exist."""


class AlreadyDecided(DomainError):
    """The item was already handled (e.g. an access request decided earlier)."""

    def __init__(self, current_status: str | None = None) -> None:
        super().__init__(current_status or "already decided")
        self.current_status = current_status


class ConfigError(RuntimeError):
    """The application cannot start because configuration is missing or invalid."""
