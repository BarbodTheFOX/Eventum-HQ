"""Main reply keyboard, built from the user's capabilities (handoff §5.2)."""

from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from eventum_hq.bot import texts
from eventum_hq.models import User
from eventum_hq.services.permissions import MenuItem, visible_menu_items

BUTTONS_PER_ROW = 2

LABEL_TO_ITEM: dict[str, MenuItem] = {label: item for item, label in texts.MENU_LABELS.items()}


def main_menu(user: User) -> ReplyKeyboardMarkup:
    labels = [texts.MENU_LABELS[item] for item in visible_menu_items(user)]
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
