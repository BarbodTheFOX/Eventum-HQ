"""M7: daily operations report — evening notes + the bot's own data → a Telegram rich message."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendMessage, SendRichMessage
from sqlalchemy import select

from eventum_hq.bot import texts
from eventum_hq.bot.daily_render import md_escape, render_html, render_markdown
from eventum_hq.bot.keyboards.daily import DailyAction, DailyCb
from eventum_hq.core.db import Database
from eventum_hq.core.errors import PermissionDenied, ValidationFailed
from eventum_hq.models import (
    ApprovalChain,
    AuditEvent,
    ContentItem,
    ContentStatus,
    ContentSubtype,
    ContentType,
    DailyNote,
    Output,
    OutputType,
    ReviewStage,
    Submission,
    Role,
    Task,
    TaskKind,
    TaskStatus,
    User,
)
from eventum_hq.services.daily_report import (
    DailyReportService,
    SectionKind,
    parse_notes,
    report_day,
)
from eventum_hq.services.permissions import ROLE_DEFAULT_CAPABILITIES, MenuItem
from tests.conftest import OWNER_TG, FakeClock, add_user
from tests.integration.test_bot_flows import AMIN, FARID, SINA, Harness, _detach_routers

SAMPLE = """#انتشار
اینستاگرام:
- ۱ پست کاروسل منتشر شد.
- رشته‌استوری روزانه منتشر شد.
سایت:
مقاله جدید در وب‌سایت منتشر شد.
#ویدیو
اصلاحات نهایی ویدیو انجام شد.
وضعیت فعلی: در مرحلهٔ تکمیل اطلاعات انتشار
#Eventum HQ
وضعیت: تکمیل v0
> نسخهٔ اولیه از نظر توسعه تکمیل شده.
#ساعت
امین ۶
محدثه مرخصی
فرید: 7.5
"""


@pytest.fixture
async def team(db: Database, owner: User) -> dict[str, User]:
    people = {"barbod": owner}
    for key, tg, role, name in [("farid", FARID, Role.DIRECTOR, "فرید"), ("amin", AMIN, Role.CONTENT_SPECIALIST, "امین"),
                                ("sina", SINA, Role.EDITOR, "سینا")]:
        people[key] = await add_user(db, telegram_id=tg, role=role, full_name=name,
                                     capabilities=list(ROLE_DEFAULT_CAPABILITIES[role]))
    return people


@pytest.fixture
def daily(db: Database, clock: FakeClock) -> DailyReportService:
    return DailyReportService(db, clock)


async def _all(db: Database, model):  # type: ignore[no-untyped-def]
    async with db.read() as s:
        return list((await s.execute(select(model).order_by(model.id))).scalars())


# ---- parsing (pure) ----------------------------------------------------------------------------


def test_parse_sections_groups_labels_and_hours() -> None:
    notes = parse_notes([SAMPLE, "#باز\nکاور ریل‌ها:\nسه ریل آخر کاور ندارند\n#ویدئوی هفتگی\n- لوگوی اسپانسر اضافه شد"])
    kinds = [s.kind for s in notes.sections]
    assert kinds == [SectionKind.PUBLISHING, SectionKind.VIDEO, SectionKind.CUSTOM, SectionKind.PENDING]

    publishing = notes.section(SectionKind.PUBLISHING)
    assert [g.title for g in publishing.groups] == ["اینستاگرام", "سایت"]
    assert [i.text for i in publishing.groups[0].items] == ["۱ پست کاروسل منتشر شد.", "رشته‌استوری روزانه منتشر شد."]

    video = notes.section(SectionKind.VIDEO)  # «ویدئوی هفتگی» from the 2nd message merged in
    items = video.groups[0].items
    assert [(i.label, i.text) for i in items] == [
        (None, "اصلاحات نهایی ویدیو انجام شد."),
        ("وضعیت فعلی", "در مرحلهٔ تکمیل اطلاعات انتشار"),
        (None, "لوگوی اسپانسر اضافه شد"),
    ]
    custom = notes.custom[0]
    assert custom.title == "Eventum HQ"
    assert custom.groups[0].items[1].paragraph is True

    assert [(r.name, r.value, r.hours) for r in notes.hours] == [
        ("امین", "", 6.0), ("محدثه", "مرخصی", None), ("فرید", "", 7.5)]
    assert notes.total_hours == 13.5


def test_parse_edge_cases() -> None:
    notes = parse_notes(["بدون عنوان\nhttps://example.com/a_b\n#\n#ساعات کاری\nسینا ۴ ساعت\nباربد"])
    assert notes.sections[0].kind == SectionKind.NOTES
    texts_ = [(i.label, i.text) for i in notes.sections[0].groups[0].items]
    assert texts_ == [(None, "بدون عنوان"), (None, "https://example.com/a_b"), (None, "#")]  # a URL is no label
    assert [(r.name, r.hours) for r in notes.hours] == [("سینا", 4.0), ("باربد", None)]
    assert notes.total_hours is None  # a total needs at least two numbers
    assert parse_notes([]).sections == [] and parse_notes(["#باز\n\n"]).sections == []


def test_report_day_cutoff_is_five_am_tehran() -> None:
    # 2026-11-12 is Thursday 1405/08/21; Tehran = UTC+3:30
    assert report_day(datetime(2026, 11, 12, 19, 0, tzinfo=UTC)) == date(2026, 11, 12)  # 22:30
    assert report_day(datetime(2026, 11, 12, 22, 0, tzinfo=UTC)) == date(2026, 11, 12)  # 01:30 next day
    assert report_day(datetime(2026, 11, 13, 1, 31, tzinfo=UTC)) == date(2026, 11, 13)  # 05:01


def test_md_escape_keeps_links_and_neutralises_markdown() -> None:
    assert md_escape("**bold** | #tag") == r"\*\*bold\*\* \| \#tag"
    assert md_escape("1. اول") == r"1\. اول"
    assert md_escape("- خط") == r"\- خط"
    assert md_escape("لینک https://x.com/a_b|c") == "لینک https://x.com/a_b%7Cc"


# ---- service ---------------------------------------------------------------------------------


async def test_notes_permissions_cutoff_and_clear(db: Database, clock: FakeClock, team, daily) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(PermissionDenied):
        await daily.add_note(team["amin"], "یادداشت")
    with pytest.raises(ValidationFailed, match="daily_note_empty"):
        await daily.add_note(team["barbod"], "   ")
    with pytest.raises(ValidationFailed, match="daily_note_too_long"):
        await daily.add_note(team["barbod"], "ا" * 4001)

    clock._now = datetime(2026, 11, 12, 19, 0, tzinfo=UTC)  # Thursday 22:30 Tehran
    assert await daily.add_note(team["barbod"], "#انتشار\nپست منتشر شد") == 1
    assert await daily.add_note(team["farid"], "#باز\nتترلند") == 2  # the DIRECTOR may write too
    clock._now = datetime(2026, 11, 12, 22, 30, tzinfo=UTC)  # Friday 02:00 → still Thursday's report
    assert await daily.add_note(team["barbod"], "#ساعت\nامین ۶") == 3
    notes = await _all(db, DailyNote)
    assert {n.report_date for n in notes} == {date(2026, 11, 12)}
    authors = await daily.authors(team["barbod"], notes)
    assert {u.full_name for u in authors.values()} == {team["barbod"].full_name, "فرید"}

    assert await daily.clear_my_notes(team["barbod"]) == 2  # Farid's note stays
    assert [n.author_id for n in await _all(db, DailyNote)] == [team["farid"].id]
    actions = [e.action for e in await _all(db, AuditEvent) if e.entity_type == "daily_report"]
    assert actions == ["daily_note.added"] * 3 + ["daily_note.cleared"]


async def test_build_merges_bot_data(db: Database, clock: FakeClock, team, daily) -> None:  # type: ignore[no-untyped-def]
    now = clock.now()  # Saturday 2026-11-07 11:30 Tehran
    async with db.transaction() as s:
        published = ContentItem(code="R-0001", type=ContentType.REEL, subtype=ContentSubtype.NORMAL,
                                title="ریل بیت‌کوین", created_by=team["barbod"].id, status=ContentStatus.PUBLISHED,
                                published_at=now - timedelta(hours=2), publish_links=[])
        old = ContentItem(code="R-0002", type=ContentType.REEL, subtype=ContentSubtype.NORMAL, title="دیروز",
                          created_by=team["barbod"].id, status=ContentStatus.PUBLISHED,
                          published_at=now - timedelta(days=1), publish_links=[])
        waiting = ContentItem(code="R-0003", type=ContentType.REEL, subtype=ContentSubtype.TRIAL, title="بدون کاور",
                              created_by=team["barbod"].id, status=ContentStatus.IN_PRODUCTION, publish_links=[])
        s.add_all([published, old, waiting])
        await s.flush()

        def task(code: str, **kw) -> Task:  # type: ignore[no-untyped-def]
            base = dict(code=code, kind=TaskKind.GENERIC, title=code, assignee_id=team["sina"].id,
                        created_by=team["farid"].id, status=TaskStatus.TODO, approval_chain=ApprovalChain.NONE)
            base.update(kw)
            return Task(**base)

        s.add_all([
            task("T-0001", title="تامنیل دیرکرده", due_at=now - timedelta(days=1)),  # overdue
            task("T-0002", status=TaskStatus.IN_REVIEW, review_stage=ReviewStage.FINAL,
                 approval_chain=ApprovalChain.FINAL, first_submitted_at=now - timedelta(hours=1),
                 due_at=now + timedelta(days=1)),  # delivered today + awaiting final approval
            task("T-0003", kind=TaskKind.COVER, content_item_id=waiting.id, assignee_id=team["amin"].id,
                 status=TaskStatus.BLOCKED, due_at=now + timedelta(days=2)),  # reel without cover
        ])
        await s.flush()
        delivered = (await s.execute(select(Task).where(Task.code == "T-0002"))).scalar_one()
        submission = Submission(task_id=delivered.id, version=1, submitted_by=team["sina"].id,
                                submitted_at=now - timedelta(hours=1))
        s.add(submission)
        await s.flush()
        s.add(Output(task_id=delivered.id, submission_id=submission.id, content_item_id=None,
                     output_type=OutputType.OTHER, title="x", owner_id=team["sina"].id,
                     approved_at=now - timedelta(minutes=5)))

    report = await daily.build(team["barbod"])
    auto = report.auto
    assert [i.code for i in auto.published] == ["R-0001"]
    assert auto.outputs == {OutputType.OTHER: 1}
    assert [(u.full_name, [t.code for t in ts]) for u, ts in auto.delivered] == [("سینا", ["T-0002"])]
    assert [line.task.code for line in auto.overdue] == ["T-0001"]
    assert auto.awaiting_final == 1
    assert [i.code for i in auto.reels_without_cover] == ["R-0003"]
    assert report.note_count == 0 and not report.empty

    md = render_markdown(report)
    assert "ریل «ریل بیت‌کوین» (R-0001) منتشر شد." in md
    assert "T-0001 «تامنیل دیرکرده» — سینا" in md
    assert "R-0003" in md and "دیروز" not in md
    with pytest.raises(PermissionDenied):
        await daily.build(team["amin"])


async def test_render_matches_the_team_report_shape(clock: FakeClock, team, daily) -> None:  # type: ignore[no-untyped-def]
    clock._now = datetime(2026, 11, 12, 19, 0, tzinfo=UTC)  # Thursday 21 Aban 1405
    await daily.add_note(team["barbod"], SAMPLE)
    await daily.add_note(team["barbod"], "#باز\nهمکاری با تترلند:\nاقدام بعدی: جلسهٔ داخلی")
    report = await daily.build(team["barbod"])
    md = render_markdown(report)
    lines = md.splitlines()
    assert lines[0] == "# EVENTUM SPACE" and lines[1] == "### DAILY OPERATIONS REPORT"
    assert lines[2] == "پنجشنبه ۲۱ آبان ۱۴۰۵ \\| ⁦12 November 2026⁩"
    headings = [line for line in lines if line.startswith("## ")]
    assert headings == [
        r"## 01 \| Content & Publishing — انتشار محتوا",
        r"## 02 \| Weekly Video — ویدیوی هفتگی",
        r"## 03 \| Eventum HQ",
        r"## 04 \| Pending & Follow-ups — موارد باز",
        r"## 05 \| Team Working Hours — ساعات کاری تیم",
    ]
    assert "#### اینستاگرام" in lines and "- ۱ پست کاروسل منتشر شد." in lines
    assert "- **وضعیت فعلی:** در مرحلهٔ تکمیل اطلاعات انتشار" in lines
    assert "نسخهٔ اولیه از نظر توسعه تکمیل شده." in lines  # a paragraph, not a list item
    assert "- **اقدام بعدی:** جلسهٔ داخلی" in lines
    assert texts.DAILY_HOURS_HEADER in lines
    assert "| ۱ | امین | ۶ ساعت |" in lines and "| ۲ | محدثه | مرخصی |" in lines
    assert "|  | **جمع** | **۱۳٫۵ ساعت** |" in lines
    assert lines[-1] == r"\#گزارش\_روزانه \#پنجشنبه \#۲۱\_آبان\_۱۴۰۵"

    html = render_html(report)
    assert "<b>01 | Content &amp; Publishing — انتشار محتوا</b>" in html
    assert "• ۱ پست کاروسل منتشر شد." in html and "۱. امین — ۶ ساعت" in html


# ---- bot flow ---------------------------------------------------------------------------------


@pytest.fixture
async def h(db: Database, clock: FakeClock, team):  # type: ignore[no-untyped-def]
    _detach_routers()
    harness = Harness(db, clock)
    yield harness
    _detach_routers()


LABEL = texts.MENU_LABELS[MenuItem.DAILY_REPORT]


def _rich(h: Harness) -> list[SendRichMessage]:
    return [c for c in h.session.calls if isinstance(c, SendRichMessage)]


async def test_bot_notes_preview_and_final(db: Database, h: Harness) -> None:
    await h.text(OWNER_TG, LABEL)
    assert "گزارش روزانه" in h.last_text(OWNER_TG)
    await h.text(OWNER_TG, "#انتشار\nاینستاگرام:\n۱ پست کاروسل منتشر شد")
    assert h.last_text(OWNER_TG).startswith("✅ ثبت شد. یادداشت‌های امروز: ۱")
    await h.text(OWNER_TG, "#ساعت\nامین ۶")
    assert "یادداشت‌های امروز: ۲" in h.last_text(OWNER_TG)
    assert len(await _all(db, DailyNote)) == 2

    h.clear()
    await h.press(OWNER_TG, DailyCb(action=DailyAction.PREVIEW).pack())
    [preview] = _rich(h)
    assert preview.chat_id == OWNER_TG and preview.rich_message.is_rtl
    assert "#### اینستاگرام" in preview.rich_message.markdown
    assert preview.reply_markup is not None  # ✅ final / ✍️ add
    assert h.last_text(OWNER_TG) == texts.DAILY_PREVIEW_HINT

    h.clear()
    await h.press(OWNER_TG, DailyCb(action=DailyAction.FINAL).pack())
    [final] = _rich(h)
    assert final.reply_markup is None and final.rich_message.markdown == preview.rich_message.markdown
    assert h.last_text(OWNER_TG) == texts.DAILY_FINAL_DONE
    sent = [e for e in await _all(db, AuditEvent) if e.action == "daily_report.sent"]
    assert len(sent) == 1 and sent[0].data["notes"] == 2

    # the flow ended with the final report: free text is no longer a note
    await h.text(OWNER_TG, "یک متن")
    assert len(await _all(db, DailyNote)) == 2


async def test_bot_menu_buttons_and_commands_still_work_in_notes(db: Database, h: Harness) -> None:
    await h.text(OWNER_TG, LABEL)
    await h.text(OWNER_TG, texts.MENU_LABELS[MenuItem.HELP])
    await h.text(OWNER_TG, "/menu")
    assert await _all(db, DailyNote) == []


async def test_bot_list_clear_and_empty_preview(db: Database, h: Harness) -> None:
    await h.press(OWNER_TG, DailyCb(action=DailyAction.PREVIEW).pack())
    assert h.alerts()[-1] == texts.DAILY_NOTHING_TO_REPORT

    await h.text(OWNER_TG, LABEL)
    await h.text(OWNER_TG, "#باز\n<b>تست</b>")
    h.clear()
    await h.press(OWNER_TG, DailyCb(action=DailyAction.LIST).pack())
    assert "&lt;b&gt;تست&lt;/b&gt;" in h.last_text(OWNER_TG)  # user text is escaped

    await h.press(OWNER_TG, DailyCb(action=DailyAction.CLEAR_ASK).pack())
    assert "۱ تا" in h.last_text(OWNER_TG)
    await h.press(OWNER_TG, DailyCb(action=DailyAction.CLEAR_YES).pack())
    assert h.last_text(OWNER_TG) == texts.DAILY_CLEARED.format(count="۱")
    assert await _all(db, DailyNote) == []


async def test_bot_others_cannot_use_daily_report(db: Database, h: Harness) -> None:
    await h.text(AMIN, LABEL)
    assert h.last_text(AMIN) == texts.PERMISSION_DENIED
    await h.press(AMIN, DailyCb(action=DailyAction.PREVIEW).pack())
    assert h.alerts()[-1] == texts.PERMISSION_DENIED
    assert await _all(db, DailyNote) == []


async def test_bot_falls_back_to_html_when_rich_message_is_refused(db: Database, h: Harness, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    original = h.session.make_request

    async def refuse_rich(bot, method, timeout=None):  # type: ignore[no-untyped-def]
        if isinstance(method, SendRichMessage):
            h.session.calls.append(method)
            raise TelegramBadRequest(method=method, message="Bad Request: can't parse rich message")
        return await original(bot, method, timeout)

    monkeypatch.setattr(h.session, "make_request", refuse_rich)
    await h.text(OWNER_TG, LABEL)
    await h.text(OWNER_TG, "#انتشار\nپست منتشر شد")
    h.clear()
    await h.press(OWNER_TG, DailyCb(action=DailyAction.FINAL).pack())
    sent = [c.text for c in h.session.calls if isinstance(c, SendMessage)]
    assert any("<b>EVENTUM SPACE</b>" in t and "• پست منتشر شد" in t for t in sent)
    assert texts.DAILY_RICH_FALLBACK in sent and sent[-1] == texts.DAILY_FINAL_DONE
    assert len([e for e in await _all(db, AuditEvent) if e.action == "daily_report.sent"]) == 1
