"""M3 end to end through the real Dispatcher: a reel from creation to publication."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from aiogram.methods import CopyMessage, SendMessage
from sqlalchemy import select

from eventum_hq.bot import texts
from eventum_hq.bot.formatters import format_jalali_date
from eventum_hq.core.db import Database
from eventum_hq.models import (
    ContentItem,
    ContentStatus,
    ReviewStage,
    Role,
    Series,
    Task,
    TaskKind,
    TaskStatus,
    User,
)
from eventum_hq.services.permissions import ROLE_DEFAULT_CAPABILITIES, MenuItem
from tests.conftest import OWNER_TG, FakeClock, add_user
from tests.integration.test_bot_flows import AMIN, ARCHIVE, FARID, SINA, Harness, _detach_routers
from tests.integration.test_bot_m2 import _calls, _media

MOHADESEH = 2004


@pytest.fixture
async def h(db: Database, clock: FakeClock, owner):  # type: ignore[no-untyped-def]
    for tg, role, name in [(FARID, Role.DIRECTOR, "Farid"), (SINA, Role.EDITOR, "Sina"),
                           (AMIN, Role.CONTENT_SPECIALIST, "Amin"), (MOHADESEH, Role.DESIGNER, "Mohadeseh")]:
        await add_user(db, telegram_id=tg, role=role, full_name=name,
                       capabilities=list(ROLE_DEFAULT_CAPABILITIES[role]))
    async with db.transaction() as s:
        s.add_all([Series(name="ریل روزانه", kind="REEL", is_active=True),
                   Series(name="Trial Reels", kind="REEL", is_active=True)])
    _detach_routers()
    harness = Harness(db, clock)
    yield harness
    _detach_routers()


async def _user(db: Database, tg: int) -> User:
    async with db.read() as s:
        return (await s.execute(select(User).where(User.telegram_id == tg))).scalar_one()


async def _items(db: Database) -> list[ContentItem]:
    async with db.read() as s:
        return list((await s.execute(select(ContentItem).order_by(ContentItem.id))).scalars())


async def _reel_tasks(db: Database) -> dict[TaskKind, Task]:
    async with db.read() as s:
        tasks = list((await s.execute(select(Task).where(Task.content_item_id.is_not(None)))).scalars())
    return {t.kind: t for t in tasks}


async def _create_reel_via_bot(h: Harness, db: Database, *, change_photos_deadline: bool = False) -> ContentItem:
    sina, mohadeseh = await _user(db, SINA), await _user(db, MOHADESEH)
    await h.text(AMIN, texts.MENU_LABELS[MenuItem.NEW_REEL])
    assert h.last_text(AMIN).startswith("➕")
    await h.text(AMIN, "ریل بیت‌کوین")
    assert h.last_text(AMIN) == texts.NEW_REEL_SUBTYPE
    await h.press(AMIN, "nr:sub:NORMAL")
    assert h.last_text(AMIN) == texts.NEW_REEL_EDIT_TYPE
    await h.press(AMIN, "nr:et:motion")
    assert h.last_text(AMIN) == texts.NEW_REEL_SERIES
    daily = next(s for s in await h.tasks.active_series() if s.name == "ریل روزانه")
    await h.press(AMIN, f"nr:ser:{daily.id}")
    assert h.last_text(AMIN) == texts.NEW_REEL_PUBLISH_PROMPT
    await h.text(AMIN, "1405/08/20 20:00")  # 2026-11-11 16:30 UTC
    assert h.last_text(AMIN) == texts.NEW_REEL_TIMECODES
    await h.text(AMIN, "00:10-00:40 و 01:20-01:35")
    assert h.last_text(AMIN) == texts.NEW_REEL_COVER_TEXT
    await h.text(AMIN, "بیت‌کوین ۱۰۰ هزار؟")
    assert h.last_text(AMIN) == texts.NEW_REEL_EDIT_ASSIGNEE
    await h.press(AMIN, f"nr:ea:{sina.id}")
    assert h.last_text(AMIN) == texts.NEW_REEL_COVER_ASSIGNEE
    await h.press(AMIN, f"nr:ca:{mohadeseh.id}")
    summary = h.last_text(AMIN)
    assert summary.startswith("🧾") and "۱ ساعت و ۴۰ دقیقه" in summary  # motion edit = 100 min

    if change_photos_deadline:
        await h.press(AMIN, "nr:dls:")
        await h.press(AMIN, "nr:dl:photos")
        await h.text(AMIN, "1405/08/17 12:00")
        assert h.last_text(AMIN).startswith("🧾")
        await h.press(AMIN, "nr:ests:")
        await h.press(AMIN, "nr:ek:cover")
        await h.text(AMIN, "۳۰")
        assert "۳۰ دقیقه" in h.last_text(AMIN)

    await h.press(AMIN, "nr:create:")
    return (await _items(db))[-1]


async def test_reel_created_from_bot(h: Harness, db: Database) -> None:
    item = await _create_reel_via_bot(h, db)
    assert item.code == "R-0001" and item.status == ContentStatus.IN_PRODUCTION
    assert item.planned_publish_at == datetime(2026, 11, 11, 16, 30, tzinfo=UTC)
    tasks = await _reel_tasks(db)
    assert tasks[TaskKind.EDIT].status == TaskStatus.TODO and tasks[TaskKind.EDIT].estimated_minutes == 100
    assert tasks[TaskKind.COVER].status == TaskStatus.BLOCKED
    assert any("R-0001" in t for t in h.texts_to(AMIN))
    sina_card = h.texts_to(SINA)[-1]
    assert "00:10-00:40" in sina_card and "عکس‌های کاور" in sina_card
    designer_card = h.texts_to(MOHADESEH)[-1]
    assert texts.BLOCKED_REASONS["waiting_cover_photos"] in designer_card
    assert "بیت‌کوین ۱۰۰ هزار؟" in designer_card


async def test_overrides_from_summary(h: Harness, db: Database) -> None:
    item = await _create_reel_via_bot(h, db, change_photos_deadline=True)
    assert item.photos_due_at == datetime(2026, 11, 8, 8, 30, tzinfo=UTC)  # 1405/08/17 12:00 Tehran
    assert (await _reel_tasks(db))[TaskKind.COVER].estimated_minutes == 30


async def test_full_reel_to_publish(h: Harness, db: Database, clock: FakeClock) -> None:
    item = await _create_reel_via_bot(h, db)
    tasks = await _reel_tasks(db)
    edit, cover = tasks[TaskKind.EDIT], tasks[TaskKind.COVER]
    h.clear()

    # ---- Sina sends cover photos from his edit card
    await h.press(SINA, f"t:ph:{edit.id}:0")
    assert "عکس‌های کاور R-0001" in h.last_text(SINA)
    await _media(h, SINA, "document", "DOC1")  # photos sent "as file" are common for covers
    await _media(h, SINA, "document", "DOC2")
    await h.press(SINA, "ph:done")
    archived = [c for c in _calls(h, CopyMessage) if c.chat_id == ARCHIVE]
    assert len(archived) == 2 and archived[0].caption.startswith("#R0001 عکس کاور")
    assert (await _reel_tasks(db))[TaskKind.COVER].status == TaskStatus.TODO
    assert any("عکس‌های کاور ریل R-0001 رسید" in t for t in h.texts_to(MOHADESEH))
    assert [c for c in _calls(h, CopyMessage) if c.chat_id == MOHADESEH]  # photos forwarded from archive

    # ---- both tasks through Amin (L1) and Farid (FINAL)
    sina, mohadeseh = await _user(db, SINA), await _user(db, MOHADESEH)
    amin, farid = await _user(db, AMIN), await _user(db, FARID)
    video = {"type": "video", "file_id": "V", "archive_message_id": 31}
    for task, person in ((edit, sina), (cover, mohadeseh)):
        sub = await h.reviews.submit(person, task.id, attachments=[video], links=[], note=None)
        await h.reviews.approve(amin, sub.id, 1, ReviewStage.L1)
        await h.reviews.approve(farid, sub.id, 1, ReviewStage.FINAL)
    await h.text(FARID, "/menu")  # any update flushes the outbox
    assert (await _items(db))[0].status == ContentStatus.READY_TO_PUBLISH
    assert any("آماده انتشار" in t and "R-0001" in t for t in h.texts_to(OWNER_TG))
    assert any(texts.REEL_TASK_KIND_LABELS["EDIT"] in t for t in h.texts_to(AMIN))

    # ---- Barbod: 🚀 list, card, publish
    h.clear()
    await h.text(OWNER_TG, texts.MENU_LABELS[MenuItem.READY_TO_PUBLISH])
    assert "آماده انتشار" in h.last_text(OWNER_TG)
    await h.press(OWNER_TG, f"rl:o:{item.id}")
    assert "R-0001" in h.last_text(OWNER_TG)
    assert len([c for c in _calls(h, CopyMessage) if c.chat_id == OWNER_TG]) == 2  # video + cover
    await h.press(OWNER_TG, f"rl:p:{item.id}")
    await h.press(OWNER_TG, "pb:now")
    assert texts.PUBLISH_NO_LINKS in h.alerts()
    await h.text(OWNER_TG, "https://instagram.com/reel/abc و https://youtube.com/shorts/xyz")
    assert "۲ لینک" in h.last_text(OWNER_TG)
    await h.press(OWNER_TG, "pb:now")
    published = (await _items(db))[0]
    assert published.status == ContentStatus.PUBLISHED and published.published_at == clock.now()
    assert published.publish_links == ["https://instagram.com/reel/abc", "https://youtube.com/shorts/xyz"]
    assert any("منتشر شد" in t for t in h.texts_to(AMIN))

    # ---- R-code lookup shows the published card
    await h.text(AMIN, "r1")
    assert "منتشر شد" in h.last_text(AMIN) and "instagram.com/reel/abc" in h.last_text(AMIN)


async def test_cancel_reel_from_card(h: Harness, db: Database) -> None:
    item = await _create_reel_via_bot(h, db)
    h.clear()
    await h.text(SINA, "R-0001")
    sina_card = [c for c in _calls(h, SendMessage) if c.chat_id == SINA][-1]
    labels = [b.text for row in sina_card.reply_markup.inline_keyboard for b in row]
    assert texts.BTN_CANCEL_REEL not in labels  # Sina cannot cancel
    await h.press(SINA, f"rl:cy:{item.id}")  # forged
    assert texts.PERMISSION_DENIED in h.alerts()
    await h.press(AMIN, f"rl:c:{item.id}")
    assert "لغو شود" in h.last_text(AMIN)
    await h.press(AMIN, f"rl:cy:{item.id}")
    assert (await _items(db))[0].status == ContentStatus.CANCELLED
    tasks = await _reel_tasks(db)
    assert all(t.status == TaskStatus.CANCELLED for t in tasks.values())
    assert any("لغو شد" in t for t in h.texts_to(SINA))
    assert any("لغو شد" in t for t in h.texts_to(MOHADESEH))


async def test_reel_permissions_in_bot(h: Harness, db: Database) -> None:
    await h.text(SINA, texts.MENU_LABELS[MenuItem.NEW_REEL])
    assert h.last_text(SINA) == texts.PERMISSION_DENIED
    await h.text(AMIN, texts.MENU_LABELS[MenuItem.READY_TO_PUBLISH])
    assert h.last_text(AMIN) == texts.PERMISSION_DENIED
    await h.text(AMIN, "R-0099")
    assert h.last_text(AMIN) == texts.REEL_CODE_NOT_FOUND.format(code="R-0099")


async def test_reel_task_card_has_no_single_cancel(h: Harness, db: Database) -> None:
    await _create_reel_via_bot(h, db)
    edit = (await _reel_tasks(db))[TaskKind.EDIT]
    h.clear()
    await h.text(AMIN, edit.code)
    card = [c for c in _calls(h, SendMessage) if c.chat_id == AMIN][-1]
    labels = [b.text for row in card.reply_markup.inline_keyboard for b in row]
    assert texts.BTN_CANCEL_TASK not in labels and texts.BTN_CHANGE_DUE in labels


async def test_publish_time_question_does_not_say_deadline(h: Harness, db: Database) -> None:
    await h.text(AMIN, texts.MENU_LABELS[MenuItem.NEW_REEL])
    await h.text(AMIN, "ریل ساعت")
    await h.press(AMIN, "nr:sub:NORMAL")
    await h.press(AMIN, "nr:et:normal")
    daily = next(s for s in await h.tasks.active_series() if s.name == "ریل روزانه")
    await h.press(AMIN, f"nr:ser:{daily.id}")
    await h.text(AMIN, "1405/08/20")  # date only → the picker asks for the hour
    assert h.last_text(AMIN) == texts.TIME_PROMPT.format(date=format_jalali_date(date(2026, 11, 11)))
    assert "ددلاین" not in h.last_text(AMIN)
    await h.text(AMIN, "20:00")
    assert h.last_text(AMIN) == texts.NEW_REEL_TIMECODES
