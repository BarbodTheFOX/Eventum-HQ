"""M2 end to end through the real Dispatcher: delivery, archive copy, review, notes, done, delegation."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from aiogram.methods import AnswerCallbackQuery, CopyMessage, LeaveChat, SendMessage, SendVoice
from sqlalchemy import select

from eventum_hq.bot import texts
from eventum_hq.core.db import Database
from eventum_hq.models import (
    ApprovalChain,
    Output,
    Role,
    Submission,
    Task,
    TaskStatus,
)
from eventum_hq.services.permissions import ROLE_DEFAULT_CAPABILITIES, MenuItem
from eventum_hq.services.tasks import NewTask
from tests.conftest import OWNER_TG, FakeClock, add_user
from tests.integration.test_bot_flows import (
    AMIN,
    ARCHIVE,
    FARID,
    SINA,
    Harness,
    _create_task_via_bot,
    _detach_routers,
    _tasks,
    _user_id,
)


async def _team(db: Database) -> None:
    for tg, role, name in [(FARID, Role.DIRECTOR, "Farid"), (SINA, Role.EDITOR, "Sina"),
                           (AMIN, Role.CONTENT_SPECIALIST, "Amin")]:
        await add_user(db, telegram_id=tg, role=role, full_name=name,
                       capabilities=list(ROLE_DEFAULT_CAPABILITIES[role]))


@pytest.fixture
async def h(db: Database, clock: FakeClock, owner):  # type: ignore[no-untyped-def]
    await _team(db)
    _detach_routers()
    harness = Harness(db, clock)
    yield harness
    _detach_routers()


@pytest.fixture
async def h_no_archive(db: Database, clock: FakeClock, owner):  # type: ignore[no-untyped-def]
    await _team(db)
    _detach_routers()
    harness = Harness(db, clock, archive_channel_id=None)
    yield harness
    _detach_routers()


async def _media(h: Harness, tg: int, kind: str, file_id: str, caption: str | None = None) -> None:
    h._n += 1
    media: dict[str, Any] = {"file_id": file_id, "file_unique_id": f"U{file_id}", "file_size": 10}
    if kind in ("video", "voice"):
        media["duration"] = 5
    if kind == "video":
        media.update(width=1080, height=1920)
    message: dict[str, Any] = {
        "message_id": h._n, "date": h._ts(),
        "chat": {"id": tg, "type": "private"},
        "from": {"id": tg, "is_bot": False, "first_name": f"U{tg}"},
        kind: media,
    }
    if caption:
        message["caption"] = caption
    await h.dp.feed_raw_update(h.bot, {"update_id": h._n, "message": message})


def _calls(h: Harness, cls: type) -> list:  # type: ignore[type-arg]
    return [c for c in h.session.calls if isinstance(c, cls)]


async def _subs(db: Database) -> list[Submission]:
    async with db.read() as s:
        return list((await s.execute(select(Submission).order_by(Submission.id))).scalars())


async def test_full_review_cycle(h: Harness, db: Database) -> None:
    task = await _create_task_via_bot(h)  # FINAL chain, assignee Sina
    h.clear()

    # ---- Sina delivers v1: a video + a link
    await h.press(SINA, f"t:sub:{task.id}:0")
    assert "تحویل T-0001" in h.last_text(SINA)
    await _media(h, SINA, "video", "VID1")
    await h.text(SINA, "https://youtu.be/abc نسخهٔ اول")
    assert "۱ فایل، ۱ لینک" in h.last_text(SINA)
    await h.press(SINA, "sb:send")

    archived = [c for c in _calls(h, CopyMessage) if c.chat_id == ARCHIVE]
    assert len(archived) == 1 and archived[0].from_chat_id == SINA
    assert archived[0].caption.startswith("#T0001 v1 | تامنیل اپیزود ۱۲ |")
    subs = await _subs(db)
    assert len(subs) == 1 and subs[0].links == ["https://youtu.be/abc"] and subs[0].note == "نسخهٔ اول"
    assert subs[0].attachments[0]["archive_message_id"] is not None
    assert (await _tasks(db))[0].status == TaskStatus.IN_REVIEW
    assert any("v۱" in t or "v1" in t for t in h.texts_to(SINA))

    # ---- Farid gets the review card and the file copied from the archive
    farid_texts = h.texts_to(FARID)
    assert any("بررسی T-0001" in t for t in farid_texts)
    assert [c for c in _calls(h, CopyMessage) if c.chat_id == FARID and c.from_chat_id == ARCHIVE]

    # ---- Farid asks for changes with a text + a voice note
    sub1 = subs[0]
    await h.press(FARID, f"rv:ch:{sub1.id}:1:FINAL")
    assert "یادداشت اصلاح برای T-0001" in h.last_text(FARID)
    await h.text(FARID, "رنگ‌ها تیره است")
    await _media(h, FARID, "voice", "VOICE9")
    await h.press(FARID, "rn:done")
    assert h.last_text(FARID) == texts.CHANGES_SENT.format(code="T-0001")
    t = (await _tasks(db))[0]
    assert t.status == TaskStatus.CHANGES_REQUESTED and t.revision_round == 1
    assert any("اصلاح خواسته شد" in x and "رنگ‌ها تیره است" in x for x in h.texts_to(SINA))
    assert any(v.voice == "VOICE9" and v.chat_id == SINA for v in _calls(h, SendVoice))

    # ---- v2 and approval
    await h.press(SINA, f"t:sub:{task.id}:0")
    await _media(h, SINA, "video", "VID2")
    await h.press(SINA, "sb:send")
    sub2 = (await _subs(db))[-1]
    assert sub2.version == 2
    await h.press(FARID, f"rv:ok:{sub2.id}:2:FINAL")
    assert texts.APPROVED_OK in h.alerts()
    t = (await _tasks(db))[0]
    assert t.status == TaskStatus.APPROVED
    assert any("تأیید نهایی شد" in x for x in h.texts_to(SINA))
    async with db.read() as s:
        assert len(list((await s.execute(select(Output))).scalars())) == 1

    # ---- the old v1 card is locked
    await h.press(FARID, f"rv:ok:{sub1.id}:1:FINAL")
    assert texts.REVIEW_ALREADY_DONE in h.alerts()

    # ---- 🏁 done after upload
    await h.press(SINA, f"t:done:{task.id}:0")
    assert (await _tasks(db))[0].status == TaskStatus.DONE
    assert any(x.startswith("🏁") for x in h.texts_to(FARID))


async def test_files_need_archive_but_links_do_not(h_no_archive: Harness, db: Database) -> None:
    h = h_no_archive
    task = await _create_task_via_bot(h)
    await h.press(SINA, f"t:sub:{task.id}:0")
    await _media(h, SINA, "video", "VID1")
    await h.press(SINA, "sb:send")
    assert h.last_text(SINA) == texts.ARCHIVE_NOT_CONFIGURED
    assert await _subs(db) == []
    await h.press(SINA, "sb:abort")
    await h.press(SINA, f"t:sub:{task.id}:0")
    await h.text(SINA, "https://drive.google.com/x")
    await h.press(SINA, "sb:send")
    assert len(await _subs(db)) == 1


async def test_empty_delivery_is_refused(h: Harness, db: Database) -> None:
    task = await _create_task_via_bot(h)
    await h.press(SINA, f"t:sub:{task.id}:0")
    await h.press(SINA, "sb:send")
    assert texts.SUBMIT_EMPTY in h.alerts()
    assert await _subs(db) == []


async def test_none_chain_done_button(h: Harness, db: Database, clock: FakeClock) -> None:
    farid = await _user_id(db, FARID)
    sina = await _user_id(db, SINA)
    async with db.read() as s:
        from eventum_hq.models import User
        farid_user = await s.get(User, farid)
    task = await h.tasks.create_generic(farid_user, NewTask(
        title="خرید تجهیزات", assignee_id=sina, due_at=clock.now() + timedelta(days=1),
        approval_chain=ApprovalChain.NONE))
    await h.text(SINA, task.code)
    card = [c for c in h.session.calls if isinstance(c, SendMessage) and c.chat_id == SINA][-1]
    labels = [b.text for row in card.reply_markup.inline_keyboard for b in row]
    assert texts.BTN_MARK_DONE in labels and texts.BTN_SUBMIT not in labels
    await h.press(SINA, f"t:sub:{task.id}:0")  # forged: delivery is not allowed for NONE
    assert texts.TASK_STATE_CHANGED in h.alerts()
    await h.press(SINA, f"t:done:{task.id}:0")
    assert (await _tasks(db))[-1].status == TaskStatus.DONE


async def test_amin_l1_queue_and_review_card(h: Harness, db: Database, clock: FakeClock) -> None:
    async with db.read() as s:
        from eventum_hq.models import User
        farid = await s.get(User, await _user_id(db, FARID))
        sina = await s.get(User, await _user_id(db, SINA))
    task = await h.tasks.create_generic(farid, NewTask(
        title="ادیت ریل", assignee_id=sina.id, due_at=clock.now() + timedelta(days=1),
        approval_chain=ApprovalChain.L1_FINAL))
    await h.reviews.submit(sina, task.id, attachments=[{"type": "video", "file_id": "V", "archive_message_id": 9}],
                           links=[], note=None)
    h.clear()
    await h.text(AMIN, texts.MENU_LABELS[MenuItem.REVIEW_QUEUE])
    assert "T-0001" in h.last_text(AMIN)
    await h.press(AMIN, f"rv:o:{task.id}:0:")
    assert "بررسی T-0001" in h.last_text(AMIN) and "مرحلهٔ اول" in h.last_text(AMIN)
    await h.press(AMIN, f"rv:d:{task.id}:0:")  # details: Amin may open L1_FINAL tasks
    assert "T-0001" in h.last_text(AMIN)
    await h.text(SINA, texts.MENU_LABELS[MenuItem.REVIEW_QUEUE])
    assert h.last_text(SINA) == texts.PERMISSION_DENIED


async def test_delegation_from_team_menu(h: Harness, db: Database) -> None:
    amin_id = await _user_id(db, AMIN)
    await h.text(AMIN, texts.MENU_LABELS[MenuItem.APPROVAL_QUEUE])
    assert h.last_text(AMIN) == texts.PERMISSION_DENIED

    await h.text(FARID, texts.MENU_LABELS[MenuItem.TEAM])
    assert texts.TEAM_NO_DELEGATION in h.last_text(FARID)
    await h.press(FARID, "tm:newdel:0")
    assert h.last_text(FARID) == texts.DELEGATION_PICK
    await h.press(FARID, f"tm:pick:{amin_id}")
    await h.press(FARID, "dt:q:tomorrow")
    await h.press(FARID, "dt:t:1800")
    assert any("تفویض شد" in t for t in h.texts_to(FARID))
    assert any(t.startswith("🔁") for t in h.texts_to(AMIN))

    await h.text(AMIN, texts.MENU_LABELS[MenuItem.APPROVAL_QUEUE])
    assert h.last_text(AMIN) == texts.QUEUE_EMPTY  # allowed now

    current = await h.delegations.current()
    assert current is not None
    await h.press(FARID, f"tm:revoke:{current.delegation.id}")
    assert any(texts.DELEGATION_REVOKED in t for t in h.texts_to(FARID))
    assert any(t.startswith("⛔️ <b>") for t in h.texts_to(AMIN))  # Amin is told too
    await h.text(AMIN, texts.MENU_LABELS[MenuItem.APPROVAL_QUEUE])
    assert h.last_text(AMIN) == texts.PERMISSION_DENIED


async def test_editor_cannot_open_team_or_delegate(h: Harness, db: Database) -> None:
    await h.text(SINA, texts.MENU_LABELS[MenuItem.TEAM])
    assert h.last_text(SINA) == texts.PERMISSION_DENIED
    await h.press(SINA, "tm:newdel:0")
    assert texts.PERMISSION_DENIED in h.alerts()


async def test_channel_and_group_ids_are_sent_to_owner(h: Harness) -> None:
    def member_update(chat: dict[str, Any], status: str) -> dict[str, Any]:
        h._n += 1
        bot_user = {"id": 42, "is_bot": True, "first_name": "Bot"}
        return {"update_id": h._n, "my_chat_member": {
            "chat": chat, "from": {"id": OWNER_TG, "is_bot": False, "first_name": "B"},
            "date": h._ts(),
            "old_chat_member": {"status": "left", "user": bot_user},
            "new_chat_member": {"status": status, "user": bot_user},
        }}

    await h.dp.feed_raw_update(h.bot, member_update({"id": -1007, "type": "supergroup", "title": "Team"}, "member"))
    assert any("-1007" in t and "TEAM_GROUP_ID" in t for t in h.texts_to(OWNER_TG))
    assert not _calls(h, LeaveChat)  # TEAM_GROUP_ID is empty: stay

    await h.dp.feed_raw_update(h.bot, member_update({"id": -1008, "type": "channel", "title": "Arch"}, "member"))
    assert any("-1008" in t and "ARCHIVE_CHANNEL_ID" in t for t in h.texts_to(OWNER_TG))


def test_review_callback_data_fits_telegram_limit() -> None:
    from eventum_hq.bot.keyboards.tasks import ReviewAction, ReviewCb

    packed = ReviewCb(action=ReviewAction.APPROVE, submission_id=999999, version=99, stage="FINAL").pack()
    assert len(packed.encode()) <= 64
    assert not [c for c in [AnswerCallbackQuery, SendMessage] if c is None]
