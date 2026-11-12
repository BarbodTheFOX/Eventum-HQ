"""M4: 📚 library — service (lists, filters, normalized search) and the bot flow."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from aiogram.methods import CopyMessage

from eventum_hq.bot import texts
from eventum_hq.bot.keyboards.library import LibAction, LibCb
from eventum_hq.core.db import Database
from eventum_hq.core.errors import NotFound, PermissionDenied
from eventum_hq.models import (
    AccessStatus,
    ApprovalChain,
    ContentItem,
    ContentStatus,
    ContentSubtype,
    ContentType,
    Output,
    OutputType,
    ReviewStage,
    Role,
    Series,
    Submission,
    Task,
    TaskKind,
    TaskStatus,
    User,
)
from eventum_hq.services.outputs import LibraryKind, LibraryService, output_search_text, query_words
from eventum_hq.services.permissions import ROLE_DEFAULT_CAPABILITIES, MenuItem
from eventum_hq.services.reviews import ReviewService
from eventum_hq.services.tasks import NewTask, TaskService
from tests.conftest import OWNER_TG, FakeClock, add_user
from tests.integration.test_bot_flows import ARCHIVE, FARID, SINA, Harness, _detach_routers

MOHADESEH = 2004
FILE = {"type": "video", "file_id": "F1", "file_unique_id": "U1", "size": 50_000_000, "archive_message_id": 77}


@pytest.fixture
async def team(db: Database, owner: User) -> dict[str, User]:
    people = {"barbod": owner}
    for key, tg, role, name in [("farid", FARID, Role.DIRECTOR, "فرید"), ("sina", SINA, Role.EDITOR, "سینا"),
                                ("mohadeseh", MOHADESEH, Role.DESIGNER, "محدثه")]:
        people[key] = await add_user(db, telegram_id=tg, role=role, full_name=name,
                                     capabilities=list(ROLE_DEFAULT_CAPABILITIES[role]))
    return people


@pytest.fixture
async def series(db: Database) -> dict[str, Series]:
    async with db.transaction() as s:
        rows = [Series(name="ریل روزانه", kind="REEL", is_active=True),
                Series(name="PURPLE ZONE", kind="LONGFORM", is_active=True),
                Series(name="سری WEEX", kind="CAMPAIGN", is_active=True)]
        s.add_all(rows)
    return {r.name: r for r in rows}


@pytest.fixture
def library(db: Database) -> LibraryService:
    return LibraryService(db)


_counter = {"n": 0}


async def _output(db: Database, clock: FakeClock, owner: User, title: str, *,
                  output_type: OutputType = OutputType.OTHER, series: Series | None = None,
                  item: ContentItem | None = None, attachments: list | None = None,  # type: ignore[type-arg]
                  links: list[str] | None = None) -> Output:
    """Insert an approved task + submission + output directly (the approval path has its own tests)."""
    _counter["n"] += 1
    clock.advance(minutes=1)
    kind = {OutputType.REEL_VIDEO: TaskKind.EDIT, OutputType.REEL_COVER: TaskKind.COVER}.get(output_type,
                                                                                         TaskKind.GENERIC)
    async with db.transaction() as s:
        task = Task(code=f"T-{_counter['n'] + 100:04d}", kind=kind, title=title, assignee_id=owner.id,
                    created_by=owner.id, status=TaskStatus.DONE, approval_chain=ApprovalChain.FINAL,
                    series_id=series.id if series else None, content_item_id=item.id if item else None)
        s.add(task)
        await s.flush()
        sub = Submission(task_id=task.id, version=2, submitted_by=owner.id, attachments=attachments or [],
                         links=links or [], submitted_at=clock.now())
        s.add(sub)
        await s.flush()
        out = Output(task_id=task.id, submission_id=sub.id, content_item_id=task.content_item_id,
                     output_type=output_type, title=title, series_id=task.series_id, owner_id=owner.id,
                     approved_at=clock.now(),
                     search_text=output_search_text(task.code, title, series.name if series else None,
                                                    owner.full_name))
        s.add(out)
    return out


# ---- normalization of the query ------------------------------------------------------


def test_query_words_normalized() -> None:
    assert query_words("  ريل   كاور ۱۲ ") == ["ریل", "کاور", "12"]
    assert query_words("تامنیل‌ها") == ["تامنیلها"]  # ZWNJ removed (same as search_text)
    assert query_words("   ") == []


# ---- service -----------------------------------------------------------------------------


async def test_recent_is_latest_ten_newest_first(db: Database, clock: FakeClock, team, library) -> None:  # type: ignore[no-untyped-def]
    for i in range(12):
        await _output(db, clock, team["sina"], f"خروجی {i}")
    rows = await library.recent(team["mohadeseh"])
    assert len(rows) == 10
    assert rows[0].output.title == "خروجی 11" and rows[-1].output.title == "خروجی 2"
    assert rows[0].owner.id == team["sina"].id and rows[0].task_code.startswith("T-")


async def test_type_and_series_filters(db: Database, clock: FakeClock, team, series, library) -> None:  # type: ignore[no-untyped-def]
    daily, purple = series["ریل روزانه"], series["PURPLE ZONE"]
    await _output(db, clock, team["sina"], "ویدیو", output_type=OutputType.REEL_VIDEO, series=daily)
    await _output(db, clock, team["mohadeseh"], "کاور", output_type=OutputType.REEL_COVER, series=daily)
    await _output(db, clock, team["sina"], "اپیزود", series=purple)
    viewer = team["mohadeseh"]
    assert [r.output.title for r in await library.by_kind(viewer, LibraryKind.REEL)] == ["ویدیو"]
    assert [r.output.title for r in await library.by_kind(viewer, LibraryKind.COVER)] == ["کاور"]
    assert [r.output.title for r in await library.by_kind(viewer, LibraryKind.OTHER)] == ["اپیزود"]
    assert [r.output.title for r in await library.by_series(viewer, daily.id)] == ["کاور", "ویدیو"]
    # only series that have outputs are offered
    assert [s.name for s in await library.series_with_outputs(viewer)] == ["ریل روزانه", "PURPLE ZONE"]


@pytest.mark.parametrize("query", [
    "تامنیل",            # part of the title
    "تامنيل",            # Arabic yeh typed
    "یوتیوب تامنیل",      # words in any order, all must match
    "weex",              # series, case-insensitive
    "t-0042",            # code
    "سینا",              # assignee name
    "ك",                 # Arabic kaf matches Persian ک (in «کمپین»)
])
async def test_search_finds(db: Database, clock: FakeClock, team, series, library, query: str) -> None:  # type: ignore[no-untyped-def]
    async with db.transaction() as s:
        task = Task(code="T-0042", kind=TaskKind.GENERIC, title="تامنیل یوتیوب کمپین", assignee_id=team["sina"].id,
                    created_by=team["farid"].id, status=TaskStatus.APPROVED, approval_chain=ApprovalChain.FINAL)
        s.add(task)
        await s.flush()
        sub = Submission(task_id=task.id, version=1, submitted_by=team["sina"].id, attachments=[FILE], links=[],
                         submitted_at=clock.now())
        s.add(sub)
        await s.flush()
        s.add(Output(task_id=task.id, submission_id=sub.id, output_type=OutputType.OTHER, title=task.title,
                     series_id=series["سری WEEX"].id, owner_id=team["sina"].id, approved_at=clock.now(),
                     search_text=output_search_text("T-0042", task.title, "سری WEEX", "سینا")))
    rows = await library.search(team["mohadeseh"], query)
    assert [r.task_code for r in rows] == ["T-0042"]


async def test_search_misses_and_wildcards(db: Database, clock: FakeClock, team, library) -> None:  # type: ignore[no-untyped-def]
    await _output(db, clock, team["sina"], "تامنیل ۱۰۰٪")
    viewer = team["farid"]
    assert await library.search(viewer, "پادکست") == []
    assert await library.search(viewer, "تامنیل پادکست") == []  # every word must match
    assert await library.search(viewer, "%") == []  # LIKE wildcards are literal
    assert await library.search(viewer, "_") == []
    assert await library.search(viewer, "") == []
    assert len(await library.search(viewer, "100")) == 1  # Persian digits stored as Latin


async def test_detail_with_reel_publish_links(db: Database, clock: FakeClock, team, series, library) -> None:  # type: ignore[no-untyped-def]
    async with db.transaction() as s:
        item = ContentItem(code="R-0007", type=ContentType.REEL, subtype=ContentSubtype.NORMAL, title="ریل طلا",
                           created_by=team["barbod"].id, status=ContentStatus.PUBLISHED,
                           published_at=datetime(2026, 11, 7, 10, 0, tzinfo=UTC),
                           publish_links=["https://instagram.com/p/x"])
        s.add(item)
    out = await _output(db, clock, team["sina"], "ریل طلا", output_type=OutputType.REEL_VIDEO,
                        series=series["ریل روزانه"], item=item, attachments=[FILE], links=["https://drive/x"])
    detail = await library.detail(team["mohadeseh"], out.id)
    assert detail.task.title == "ریل طلا" and detail.version == 2
    assert detail.content_item is not None and detail.content_item.publish_links == ["https://instagram.com/p/x"]
    assert detail.attachments == [FILE] and detail.links == ["https://drive/x"]
    assert detail.series is not None and detail.series.name == "ریل روزانه"
    with pytest.raises(NotFound):
        await library.detail(team["mohadeseh"], 9999)


async def test_inactive_user_denied(db: Database, clock: FakeClock, team, library) -> None:  # type: ignore[no-untyped-def]
    out = await _output(db, clock, team["sina"], "x")
    gone = await add_user(db, telegram_id=3001, is_active=False)
    pending = await add_user(db, telegram_id=3002, access_status=AccessStatus.PENDING)
    for user in (gone, pending):
        with pytest.raises(PermissionDenied):
            await library.recent(user)
        with pytest.raises(PermissionDenied):
            await library.search(user, "x")
        with pytest.raises(PermissionDenied):
            await library.detail(user, out.id)


async def test_final_approval_puts_output_in_library(db: Database, clock: FakeClock, team, series, library) -> None:  # type: ignore[no-untyped-def]
    tasks, reviews = TaskService(db, clock), ReviewService(db, clock)
    task = await tasks.create_generic(team["farid"], NewTask(
        title="تامنیل اپیزود ۳", assignee_id=team["sina"].id, due_at=clock.now() + timedelta(days=1),
        series_id=series["PURPLE ZONE"].id))
    sub = await reviews.submit(team["sina"], task.id, attachments=[FILE], links=[], note=None)
    assert await library.search(team["mohadeseh"], "اپیزود") == []  # not approved yet
    await reviews.approve(team["farid"], sub.id, 1, ReviewStage.FINAL)
    rows = await library.search(team["mohadeseh"], "purple اپیزود 3")
    assert [r.task_code for r in rows] == [task.code]


# ---- bot ---------------------------------------------------------------------------------


@pytest.fixture
async def h(db: Database, clock: FakeClock, team):  # type: ignore[no-untyped-def]
    _detach_routers()
    harness = Harness(db, clock)
    yield harness
    _detach_routers()


def _lib(action: LibAction, **kw) -> str:  # type: ignore[no-untyped-def]
    return LibCb(action=action, **kw).pack()


async def test_bot_search_and_open(h: Harness, db: Database, clock: FakeClock, team) -> None:  # type: ignore[no-untyped-def]
    out = await _output(db, clock, team["sina"], "تامنیل یوتیوب", attachments=[FILE], links=["https://drive/x"])
    await h.text(MOHADESEH, texts.MENU_LABELS[MenuItem.LIBRARY])
    assert h.last_text(MOHADESEH).startswith("📚")
    await h.text(MOHADESEH, "تامنيل")  # Arabic yeh
    result = h.last_text(MOHADESEH)
    assert "تامنیل یوتیوب" in result and "۱ مورد" in result

    h.clear()
    await h.press(MOHADESEH, _lib(LibAction.OPEN, item=out.id, src=LibAction.QUERY.value))
    detail = h.last_text(MOHADESEH)
    assert "تامنیل یوتیوب" in detail and "https://drive/x" in detail and "سینا" in detail
    copies = [c for c in h.session.calls if isinstance(c, CopyMessage) and c.chat_id == MOHADESEH]
    assert len(copies) == 1 and copies[0].from_chat_id == ARCHIVE and copies[0].message_id == 77


async def test_bot_task_code_in_library_is_a_search(h: Harness, db: Database, clock: FakeClock, team) -> None:  # type: ignore[no-untyped-def]
    out = await _output(db, clock, team["sina"], "پوستر")
    async with db.read() as s:
        code = (await s.get(Task, out.task_id)).code  # type: ignore[union-attr]
    await h.text(MOHADESEH, texts.MENU_LABELS[MenuItem.LIBRARY])
    await h.text(MOHADESEH, code)
    assert texts.LIB_SEARCH_TITLE.format(query=code).split("«")[0] in h.last_text(MOHADESEH)
    assert "پوستر" in h.last_text(MOHADESEH)


async def test_bot_menu_button_leaves_library(h: Harness, db: Database, clock: FakeClock, team) -> None:  # type: ignore[no-untyped-def]
    await h.text(MOHADESEH, texts.MENU_LABELS[MenuItem.LIBRARY])
    await h.text(MOHADESEH, texts.MENU_LABELS[MenuItem.MY_TASKS])
    await h.text(MOHADESEH, "تامنیل")
    assert h.last_text(MOHADESEH) == texts.UNKNOWN_INPUT  # no longer a search


async def test_bot_library_expires_quietly(h: Harness, db: Database, clock: FakeClock, team) -> None:  # type: ignore[no-untyped-def]
    await h.text(MOHADESEH, texts.MENU_LABELS[MenuItem.LIBRARY])
    clock.advance(minutes=31)
    await h.text(MOHADESEH, "تامنیل")
    assert texts.FLOW_EXPIRED not in h.texts_to(MOHADESEH)
    assert h.last_text(MOHADESEH) == texts.UNKNOWN_INPUT


async def test_bot_lists_and_paging(h: Harness, db: Database, clock: FakeClock, team, series) -> None:  # type: ignore[no-untyped-def]
    daily = series["ریل روزانه"]
    for i in range(9):
        await _output(db, clock, team["sina"], f"ریل {i}", output_type=OutputType.REEL_VIDEO, series=daily)
    await _output(db, clock, team["mohadeseh"], "کاور تنها", output_type=OutputType.REEL_COVER)

    await h.press(SINA, _lib(LibAction.KIND, kind="reel"))
    first = h.last_text(SINA)
    assert "۹ مورد" in first and "ریل 8" in first and "ریل 0" not in first  # 8 per page, newest first
    await h.press(SINA, _lib(LibAction.KIND, kind="reel", page=1))
    assert "ریل 0" in h.last_text(SINA) and "ریل 8" not in h.last_text(SINA)

    await h.press(SINA, _lib(LibAction.KIND, kind="cover"))
    assert "کاور تنها" in h.last_text(SINA)

    await h.press(SINA, _lib(LibAction.PICK_SERIES))
    assert h.last_text(SINA) == texts.LIB_PICK_SERIES
    await h.press(SINA, _lib(LibAction.SERIES, arg=daily.id))
    assert "۹ مورد" in h.last_text(SINA)

    await h.press(SINA, _lib(LibAction.RECENT))
    assert "۱۰ مورد" in h.last_text(SINA) and "کاور تنها" in h.last_text(SINA)


async def test_bot_empty_library_and_stale_buttons(h: Harness, db: Database, clock: FakeClock, team) -> None:  # type: ignore[no-untyped-def]
    await h.press(SINA, _lib(LibAction.RECENT))
    assert texts.LIB_EMPTY_LIBRARY in h.last_text(SINA)
    await h.press(SINA, _lib(LibAction.PICK_SERIES))
    assert texts.LIB_NO_SERIES in h.alerts()
    await h.press(SINA, _lib(LibAction.QUERY))  # search text not in FSM any more
    assert texts.LIB_SEARCH_EXPIRED in h.alerts()
    await h.press(SINA, _lib(LibAction.OPEN, item=999))
    assert texts.LIB_NOT_FOUND in h.alerts()
    await h.press(SINA, _lib(LibAction.KIND, kind="bogus"))
    assert texts.STALE_BUTTON in h.alerts()


async def test_bot_owner_sees_library_too(h: Harness, db: Database, clock: FakeClock, team) -> None:  # type: ignore[no-untyped-def]
    await _output(db, clock, team["sina"], "x")
    await h.text(OWNER_TG, texts.MENU_LABELS[MenuItem.LIBRARY])
    assert h.last_text(OWNER_TG).startswith("📚")
