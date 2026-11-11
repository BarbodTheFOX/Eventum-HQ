"""M5 through the real Dispatcher: 📊 report and 🔁 recurring tasks under 👥 تیم."""

from __future__ import annotations

from aiogram.methods import EditMessageText, SendMessage
from sqlalchemy import select

from eventum_hq.bot import texts
from eventum_hq.bot.keyboards.recurrences import RecurAction, RecurCb
from eventum_hq.core.db import Database
from eventum_hq.models import Recurrence, RecurrenceRule, User
from eventum_hq.services.permissions import MenuItem
from tests.integration.test_bot_flows import FARID, SINA, Harness, h  # noqa: F401  (fixture)


def _buttons(harness: Harness, tg: int) -> list[str]:
    for call in reversed(harness.session.calls):
        if isinstance(call, (SendMessage, EditMessageText)) and call.chat_id == tg and call.reply_markup:
            markup = call.reply_markup
            if hasattr(markup, "inline_keyboard"):
                return [b.callback_data for row in markup.inline_keyboard for b in row]
    return []


async def _id(db: Database, tg: int) -> int:
    async with db.read() as s:
        return (await s.execute(select(User.id).where(User.telegram_id == tg))).scalar_one()


async def test_report_button_for_farid_only(h: Harness) -> None:
    await h.text(FARID, texts.MENU_LABELS[MenuItem.REPORT])
    assert h.last_text(FARID).startswith("📊")
    assert "بار کاری" in h.last_text(FARID)
    await h.text(SINA, texts.MENU_LABELS[MenuItem.REPORT])
    assert h.last_text(SINA) == texts.PERMISSION_DENIED


async def test_create_and_stop_a_recurrence_from_team(h: Harness, db: Database) -> None:
    await h.text(FARID, texts.MENU_LABELS[MenuItem.TEAM])
    assert RecurCb(action=RecurAction.LIST).pack() in _buttons(h, FARID)
    await h.press(FARID, RecurCb(action=RecurAction.LIST).pack())
    assert h.last_text(FARID).startswith(texts.RECURRENCES_TITLE)
    await h.press(FARID, RecurCb(action=RecurAction.NEW).pack())
    await h.text(FARID, "گزارش روزانهٔ اینستاگرام")
    assert h.last_text(FARID) == texts.NEW_RECURRENCE_ASSIGNEE
    sina_id = await _id(db, SINA)
    await h.press(FARID, RecurCb(action=RecurAction.ASSIGNEE, arg=sina_id).pack())
    await h.press(FARID, RecurCb(action=RecurAction.RULE, value="WEEKDAYS").pack())
    await h.press(FARID, RecurCb(action=RecurAction.DAYS_DONE).pack())
    assert texts.WEEKDAYS_REQUIRED in h.alerts()
    await h.press(FARID, RecurCb(action=RecurAction.DAY, arg=0).pack())
    await h.press(FARID, RecurCb(action=RecurAction.DAY, arg=2).pack())
    await h.press(FARID, RecurCb(action=RecurAction.DAYS_DONE).pack())
    assert h.last_text(FARID) == texts.NEW_RECURRENCE_CREATE_TIME
    await h.text(FARID, "۰۹:۰۰")
    assert h.last_text(FARID) == texts.NEW_RECURRENCE_DUE_TIME
    await h.press(FARID, RecurCb(action=RecurAction.DUE_TIME, value="0800").pack())  # before create time
    assert texts.VALIDATION_MESSAGES["due_before_create"] in h.last_text(FARID)
    await h.press(FARID, RecurCb(action=RecurAction.DUE_TIME, value="1800").pack())
    await h.press(FARID, RecurCb(action=RecurAction.CHAIN, value="NONE").pack())
    await h.press(FARID, RecurCb(action=RecurAction.ESTIMATE, arg=30).pack())
    assert "شنبه، دوشنبه" in h.last_text(FARID)
    await h.press(FARID, RecurCb(action=RecurAction.CREATE).pack())
    assert "گزارش روزانهٔ اینستاگرام" in h.last_text(FARID)

    async with db.read() as s:
        recurrence = (await s.execute(select(Recurrence))).scalar_one()
    assert recurrence.rule == RecurrenceRule.WEEKDAYS and recurrence.weekdays == [0, 2]
    assert recurrence.assignee_id == sina_id and recurrence.estimated_minutes == 30

    await h.press(FARID, RecurCb(action=RecurAction.STOP, arg=recurrence.id).pack())
    assert h.last_text(FARID).startswith("⛔️")
    async with db.read() as s:
        assert (await s.get(Recurrence, recurrence.id)).is_active is False  # type: ignore[union-attr]


async def test_recurrence_buttons_need_create_task(h: Harness) -> None:
    await h.press(SINA, RecurCb(action=RecurAction.NEW).pack())
    assert texts.PERMISSION_DENIED in h.alerts()
    await h.press(SINA, RecurCb(action=RecurAction.LIST).pack())
    assert h.alerts().count(texts.PERMISSION_DENIED) == 2
