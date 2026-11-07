"""Small helpers that turn domain values into display strings (HTML-escaped)."""

from __future__ import annotations

from html import escape

from eventum_hq.bot import texts
from eventum_hq.models import Role


def esc(value: object) -> str:
    return escape(str(value), quote=False)


def display_name(full_name: str | None) -> str:
    name = (full_name or "").strip()
    return esc(name) if name else texts.NO_NAME


def display_username(username: str | None) -> str:
    return f"@{esc(username)}" if username else texts.NO_USERNAME


def role_label(role: Role | str | None) -> str:
    try:
        return texts.ROLE_LABELS[Role(role)] if role is not None else "—"
    except ValueError:
        return esc(role)


def access_request_card(
    *, full_name: str | None, username: str | None, telegram_id: int, role: Role | str | None
) -> str:
    return texts.ACCESS_REQUEST_CARD.format(
        name=display_name(full_name),
        username=display_username(username),
        telegram_id=int(telegram_id),
        role=role_label(role),
    )
