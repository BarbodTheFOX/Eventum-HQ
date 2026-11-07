"""Main reply keyboard, built from the user's role/capabilities (handoff §5.2)."""

from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from eventum_hq.bot import texts
from eventum_hq.models import User
from eventum_hq.services.permissions import MenuItem, visible_menu_items

BUTTONS_PER_ROW = 2

LABEL_TO_ITEM: dict[str, MenuItem] = {label: item for item, label in texts.MENU_LABELS.items()}


class AdminViews:
    """Which OWNERs currently use "admin view". In memory: resets to normal on restart."""

    def __init__(self) -> None:
        self._on: set[int] = set()

    def is_on(self, telegram_id: int) -> bool:
        return telegram_id in self._on

    def set(self, telegram_id: int, on: bool) -> None:
        if on:
            self._on.add(telegram_id)
        else:
            self._on.discard(telegram_id)


def main_menu(user: User, admin_view: bool = False) -> ReplyKeyboardMarkup:
    labels = [texts.MENU_LABELS[item] for item in visible_menu_items(user, admin_view=admin_view)]
    rows = [
        [KeyboardButton(text=label) for label in labels[i : i + BUTTONS_PER_ROW]]
        for i in range(0, len(labels), BUTTONS_PER_ROW)
    ]
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder=texts.MENU_PLACEHOLDER,
    )


def menu_for(user: User, views: AdminViews) -> ReplyKeyboardMarkup:
    return main_menu(user, admin_view=views.is_on(user.telegram_id))
