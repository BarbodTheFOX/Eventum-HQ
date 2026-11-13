"""Daily operations report (M7): the bot's own data for the day + the evening notes.

No AI: the notes are free text with a light convention, parsed by :func:`parse_notes`:

* a line that starts with ``#`` opens a section (``#انتشار``, ``#ویدیو``, ``#باز``,
  ``#ساعت`` are the fixed ones, any other name is a custom section);
* a line that ends with ``:`` is a sub-heading inside the section;
* every other line is one list item; ``عنوان: متن`` gets a bold label, a line
  that starts with ``>`` is a plain paragraph;
* under ``#ساعت`` every line is ``نام ۶`` (or ``نام: مرخصی``) and becomes a table row.

Notes of one day may come in many messages and from more than one person; the
report merges them in the order they were written. The bot layer turns the
:class:`DailyReport` into a Telegram rich message.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from enum import StrEnum

from sqlalchemy import delete, func, select

from eventum_hq.core.db import Database
from eventum_hq.core.errors import PermissionDenied, ValidationFailed
from eventum_hq.core.jalali import tehran_to_utc
from eventum_hq.core.normalize import normalize_digits, normalize_text
from eventum_hq.core.timeutil import Clock, to_tehran
from eventum_hq.models import (
    ContentItem,
    ContentStatus,
    DailyNote,
    Output,
    OutputType,
    ReviewStage,
    Task,
    TaskKind,
    TaskStatus,
    User,
)
from eventum_hq.repositories import reviews as reviews_repo
from eventum_hq.repositories import users as users_repo
from eventum_hq.services import audit
from eventum_hq.services.reports import can_receive_report
from eventum_hq.services.task_states import is_open
from eventum_hq.services.tasks import DeadlineState, deadline_state

# notes written before this Tehran hour still belong to the previous day
DAY_CUTOFF = time(5, 0)
MAX_NOTE_CHARS = 4000
MAX_NOTES_PER_DAY = 60

ENTITY = "daily_report"  # audit entity; entity_id = the report day's ordinal
ACTION_NOTE_ADDED = "daily_note.added"
ACTION_NOTES_CLEARED = "daily_note.cleared"
ACTION_REPORT_SENT = "daily_report.sent"


class SectionKind(StrEnum):
    PUBLISHING = "PUBLISHING"
    VIDEO = "VIDEO"
    CUSTOM = "CUSTOM"
    NOTES = "NOTES"  # lines written before any heading
    PENDING = "PENDING"
    HOURS = "HOURS"


# heading keywords (compared after normalize_text, so ی/ک and نیم‌فاصله do not matter)
_ALIASES: dict[str, SectionKind] = {
    key: kind
    for kind, keys in {
        SectionKind.PUBLISHING: ("انتشار", "انتشار محتوا", "محتوا", "publishing", "content"),
        SectionKind.VIDEO: ("ویدیو", "ویدئو", "ویدیو هفتگی", "ویدیوی هفتگی", "ویدئوی هفتگی", "video"),
        SectionKind.PENDING: ("باز", "موارد باز", "پیگیری", "پیگیریها", "پیگیری ها", "pending"),
        SectionKind.HOURS: ("ساعت", "ساعات", "ساعت کاری", "ساعات کاری", "hours"),
    }.items()
    for key in keys
}

_BULLET_RE = re.compile(r"^[-•*–—+▪●]\s*")
# "امین ۶", "امین: 6.5", "امین ۷ ساعت"
_HOURS_LINE_RE = re.compile(r"^(.+?)[\s:：]+(\d+(?:\.\d+)?)\s*(?:ساعت|h|hr|hrs|hours?)?$", re.IGNORECASE)
_LABEL_MAX = 40
_SUBHEADING_MAX = 60


@dataclass(slots=True)
class NoteItem:
    text: str
    label: str | None = None
    paragraph: bool = False


@dataclass(slots=True)
class NoteGroup:
    title: str | None
    items: list[NoteItem] = field(default_factory=list)


@dataclass(slots=True)
class NoteSection:
    kind: SectionKind
    title: str | None = None  # custom sections only
    groups: list[NoteGroup] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not any(g.items or g.title for g in self.groups)


@dataclass(frozen=True, slots=True)
class HoursRow:
    name: str
    value: str  # as written, e.g. "مرخصی"; empty when ``hours`` is set
    hours: float | None


@dataclass(slots=True)
class ParsedNotes:
    sections: list[NoteSection]
    hours: list[HoursRow]

    def section(self, kind: SectionKind) -> NoteSection | None:
        return next((s for s in self.sections if s.kind == kind), None)

    @property
    def custom(self) -> list[NoteSection]:
        return [s for s in self.sections if s.kind in (SectionKind.CUSTOM, SectionKind.NOTES)]

    @property
    def total_hours(self) -> float | None:
        numbers = [r.hours for r in self.hours if r.hours is not None]
        return sum(numbers) if len(numbers) >= 2 else None


@dataclass(frozen=True, slots=True)
class OverdueLine:
    task: Task
    assignee: User


@dataclass(frozen=True, slots=True)
class AutoData:
    """What the bot itself knows about the day."""

    published: list[ContentItem]
    outputs: dict[OutputType, int]
    delivered: list[tuple[User, list[Task]]]
    overdue: list[OverdueLine]
    awaiting_final: int
    reels_without_cover: list[ContentItem]

    @property
    def empty(self) -> bool:
        return not (self.published or self.outputs or self.delivered or self.overdue
                    or self.awaiting_final or self.reels_without_cover)


@dataclass(frozen=True, slots=True)
class DailyReport:
    day: date
    notes: ParsedNotes
    auto: AutoData
    note_count: int
    generated_at: datetime

    @property
    def empty(self) -> bool:
        return self.note_count == 0 and self.auto.empty


# ---- parsing (pure, unit-tested) ---------------------------------------------------------


def _heading_kind(title: str) -> SectionKind:
    return _ALIASES.get(normalize_text(title), SectionKind.CUSTOM)


def _split_label(line: str) -> tuple[str | None, str]:
    index = line.find(":")
    if 0 < index <= _LABEL_MAX:
        label, rest = line[:index].strip(), line[index + 1:].strip()
        if label and rest and "/" not in label and not rest.startswith("//"):  # not "https://…"
            return label, rest
    return None, line


def _hours_row(line: str) -> HoursRow | None:
    line = _BULLET_RE.sub("", line).strip()
    if not line:
        return None
    numeric = normalize_digits(line).replace("٫", ".")
    match = _HOURS_LINE_RE.match(numeric)
    if match:
        return HoursRow(name=match.group(1).strip(), value="", hours=float(match.group(2)))
    if ":" in line:
        name, value = (part.strip() for part in line.split(":", 1))
    else:
        head, sep, tail = line.rpartition(" ")
        name, value = (head.strip(), tail.strip()) if sep else (line, "")
    return HoursRow(name=name or value, value=value if name else "", hours=None)


def parse_notes(messages: list[str]) -> ParsedNotes:
    """Merge the day's notes into sections. Same-name sections from different messages merge."""
    sections: list[NoteSection] = []
    hours: list[HoursRow] = []

    def find(kind: SectionKind, title: str | None) -> NoteSection:
        key = normalize_text(title) if title else None
        for s in sections:
            if s.kind == kind and (kind != SectionKind.CUSTOM or normalize_text(s.title or "") == key):
                return s
        section = NoteSection(kind, title if kind == SectionKind.CUSTOM else None)
        sections.append(section)
        return section

    for message in messages:
        current: NoteSection | None = None
        group: NoteGroup | None = None
        for raw in message.splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#") and line.lstrip("#").strip():
                title = line.lstrip("#").strip()
                current = find(_heading_kind(title), title)
                group = None
                continue
            if current is None:
                current = find(SectionKind.NOTES, None)
            if current.kind == SectionKind.HOURS:
                row = _hours_row(line)
                if row is not None:
                    hours.append(row)
                continue
            if line.endswith((":", "：")) and len(line) <= _SUBHEADING_MAX:
                group = NoteGroup(title=line[:-1].strip() or None)
                current.groups.append(group)
                continue
            if group is None:
                if current.groups and current.groups[-1].title is None:
                    group = current.groups[-1]
                else:
                    group = NoteGroup(title=None)
                    current.groups.append(group)
            if line.startswith(">"):
                text = line.lstrip(">").strip()
                if text:
                    group.items.append(NoteItem(text=text, paragraph=True))
                continue
            label, text = _split_label(_BULLET_RE.sub("", line).strip())
            if text:
                group.items.append(NoteItem(text=text, label=label))

    order = {SectionKind.PUBLISHING: 0, SectionKind.VIDEO: 1, SectionKind.CUSTOM: 2, SectionKind.NOTES: 3,
             SectionKind.PENDING: 4, SectionKind.HOURS: 5}
    kept = [s for s in sections if s.kind != SectionKind.HOURS and not s.empty]
    kept.sort(key=lambda s: order[s.kind])  # stable: custom sections keep their order
    return ParsedNotes(sections=kept, hours=hours)


def report_day(now: datetime) -> date:
    """The Tehran day a note written at ``now`` belongs to (before 05:00 = yesterday)."""
    local = to_tehran(now)
    day = local.date()
    return day - timedelta(days=1) if local.time() < DAY_CUTOFF else day


# ---- service -----------------------------------------------------------------------------


class DailyReportService:
    def __init__(self, db: Database, clock: Clock) -> None:
        self._db = db
        self._clock = clock

    def today(self) -> date:
        return report_day(self._clock.now())

    async def _check(self, session, actor: User) -> User:  # type: ignore[no-untyped-def]
        fresh = await users_repo.get_by_id(session, actor.id)
        if fresh is None or not fresh.can_use_bot or not can_receive_report(fresh):
            raise PermissionDenied("daily_report")
        return fresh

    async def add_note(self, actor: User, text: str) -> int:
        """Store one note for today's report; returns how many notes the day has now."""
        text = text.strip()
        if not text:
            raise ValidationFailed("daily_note_empty")
        if len(text) > MAX_NOTE_CHARS:
            raise ValidationFailed("daily_note_too_long")
        now = self._clock.now()
        day = report_day(now)
        async with self._db.transaction() as session:
            fresh = await self._check(session, actor)
            count = await self._count(session, day)
            if count >= MAX_NOTES_PER_DAY:
                raise ValidationFailed("daily_notes_full")
            note = DailyNote(report_date=day, author_id=fresh.id, text=text)
            session.add(note)
            await session.flush()
            await audit.record(session, actor_id=fresh.id, action=ACTION_NOTE_ADDED, entity_type=ENTITY,
                               entity_id=day.toordinal(), at=now, data={"note_id": note.id, "day": day.isoformat()})
            return count + 1

    async def notes(self, actor: User, day: date | None = None) -> list[DailyNote]:
        day = day or self.today()
        async with self._db.read() as session:
            await self._check(session, actor)
            result = await session.execute(
                select(DailyNote).where(DailyNote.report_date == day).order_by(DailyNote.created_at, DailyNote.id))
            return list(result.scalars())

    async def authors(self, actor: User, notes: list[DailyNote]) -> dict[int, User]:
        async with self._db.read() as session:
            await self._check(session, actor)
            return dict(await users_repo.get_many(session, {n.author_id for n in notes}))

    async def clear_my_notes(self, actor: User) -> int:
        """Delete the actor's own notes for today (others' notes stay)."""
        now = self._clock.now()
        day = report_day(now)
        async with self._db.transaction() as session:
            fresh = await self._check(session, actor)
            result = await session.execute(
                delete(DailyNote).where(DailyNote.report_date == day, DailyNote.author_id == fresh.id))
            removed = result.rowcount or 0
            if removed:
                await audit.record(session, actor_id=fresh.id, action=ACTION_NOTES_CLEARED, entity_type=ENTITY,
                                   entity_id=day.toordinal(), at=now,
                                   data={"day": day.isoformat(), "removed": removed})
            return removed

    async def build(self, actor: User) -> DailyReport:
        now = self._clock.now()
        day = report_day(now)
        notes = await self.notes(actor, day)
        auto = await self._auto(day, now)
        return DailyReport(day=day, notes=parse_notes([n.text for n in notes]), auto=auto,
                           note_count=len(notes), generated_at=now)

    async def mark_sent(self, actor: User, report: DailyReport) -> None:
        async with self._db.transaction() as session:
            fresh = await self._check(session, actor)
            await audit.record(session, actor_id=fresh.id, action=ACTION_REPORT_SENT, entity_type=ENTITY,
                               entity_id=report.day.toordinal(), at=self._clock.now(),
                               data={"day": report.day.isoformat(), "notes": report.note_count})

    # ---- helpers ------------------------------------------------------------------------

    @staticmethod
    async def _count(session, day: date) -> int:  # type: ignore[no-untyped-def]
        result = await session.execute(select(func.count(DailyNote.id)).where(DailyNote.report_date == day))
        return int(result.scalar_one())

    async def _auto(self, day: date, now: datetime) -> AutoData:
        start = tehran_to_utc(day, time(0, 0))
        end = tehran_to_utc(day + timedelta(days=1), time(0, 0))
        async with self._db.read() as session:
            published = list((await session.execute(
                select(ContentItem).where(ContentItem.published_at >= start, ContentItem.published_at < end)
                .order_by(ContentItem.published_at, ContentItem.id))).scalars())
            outputs: dict[OutputType, int] = {}
            for output in (await session.execute(
                    select(Output).where(Output.approved_at >= start, Output.approved_at < end))).scalars():
                outputs[output.output_type] = outputs.get(output.output_type, 0) + 1
            tasks = list((await session.execute(select(Task).order_by(Task.id))).scalars())
            people = {u.id: u for u in await users_repo.list_active(session)}
            awaiting = len([t for t in await reviews_repo.tasks_in_review(session, ReviewStage.FINAL)
                            if t.assignee_id in people])
            open_items = {i.id: i for i in (await session.execute(
                select(ContentItem).where(ContentItem.status.in_(
                    (ContentStatus.IN_PRODUCTION, ContentStatus.READY_TO_PUBLISH)))
                .order_by(ContentItem.id))).scalars()}

        delivered: dict[int, list[Task]] = {}
        overdue: list[OverdueLine] = []
        missing_cover: set[int] = set()
        for t in tasks:
            at = t.first_submitted_at or (t.completed_at if t.status == TaskStatus.DONE else None)
            if at is not None and start <= at < end and t.assignee_id in people:
                delivered.setdefault(t.assignee_id, []).append(t)
            if t.assignee_id in people and deadline_state(t, now) == DeadlineState.OVERDUE:
                overdue.append(OverdueLine(t, people[t.assignee_id]))
            if t.kind == TaskKind.COVER and t.content_item_id in open_items and is_open(t.status) \
                    and t.status != TaskStatus.APPROVED:
                missing_cover.add(t.content_item_id)
        overdue.sort(key=lambda line: (line.task.due_at or now, line.task.id))
        return AutoData(
            published=published,
            outputs=outputs,
            delivered=[(people[uid], ts) for uid, ts in sorted(delivered.items())],
            overdue=overdue,
            awaiting_final=awaiting,
            reels_without_cover=[open_items[i] for i in sorted(missing_cover)],
        )
