"""📚 Library of approved outputs (F9, handoff §4.9).

Read-only: every active, approved user may browse it (§3.2). Lists are the
latest 10 outputs, a type filter (reel video / cover / other), a series filter
and a free-text search. The search is a ``LIKE`` on the normalized
``outputs.search_text`` column (task code, title, series, assignee name); each
word of the query must appear. Files are sent by the bot layer from the
archive channel, using the attachments of the approved submission.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eventum_hq.core.db import Database
from eventum_hq.core.errors import NotFound, PermissionDenied
from eventum_hq.core.normalize import normalize_text
from eventum_hq.models import ContentItem, Output, OutputType, Series, Submission, Task, User
from eventum_hq.repositories import series as series_repo
from eventum_hq.repositories import users as users_repo

RECENT_LIMIT = 10
SEARCH_LIMIT = 200  # more than enough for a 6-person team; pages of 8 in the bot
QUERY_MAX = 100


class LibraryKind(StrEnum):
    """Type filter of the library (§4.9: ریل / کاور / سایر)."""

    REEL = "reel"
    COVER = "cover"
    OTHER = "other"


KIND_TO_TYPE: dict[LibraryKind, OutputType] = {
    LibraryKind.REEL: OutputType.REEL_VIDEO,
    LibraryKind.COVER: OutputType.REEL_COVER,
    LibraryKind.OTHER: OutputType.OTHER,
}


@dataclass(frozen=True, slots=True)
class OutputRow:
    output: Output
    task_code: str
    owner: User


@dataclass(frozen=True, slots=True)
class OutputDetail:
    output: Output
    task: Task
    owner: User
    series: Series | None
    content_item: ContentItem | None
    version: int
    attachments: list[dict[str, Any]]
    links: list[str]


def _like_pattern(word: str) -> str:
    escaped = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def output_search_text(code: str, title: str, series_name: str | None, owner_name: str | None) -> str:
    """The normalized ``outputs.search_text``: task code, title, series and assignee name."""
    return normalize_text(" ".join(part for part in (code, title, series_name, owner_name) if part))


def query_words(query: str) -> list[str]:
    """Normalized search words (Persian letters/digits unified, ZWNJ removed)."""
    return normalize_text(query[:QUERY_MAX]).split()


class LibraryService:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def recent(self, viewer: User) -> list[OutputRow]:
        async with self._db.read() as session:
            await _fresh(session, viewer)
            return await self._rows(session, select(Output), RECENT_LIMIT)

    async def by_kind(self, viewer: User, kind: LibraryKind) -> list[OutputRow]:
        async with self._db.read() as session:
            await _fresh(session, viewer)
            stmt = select(Output).where(Output.output_type == KIND_TO_TYPE[kind])
            return await self._rows(session, stmt, SEARCH_LIMIT)

    async def by_series(self, viewer: User, series_id: int) -> list[OutputRow]:
        async with self._db.read() as session:
            await _fresh(session, viewer)
            stmt = select(Output).where(Output.series_id == series_id)
            return await self._rows(session, stmt, SEARCH_LIMIT)

    async def search(self, viewer: User, query: str) -> list[OutputRow]:
        words = query_words(query)
        async with self._db.read() as session:
            await _fresh(session, viewer)
            if not words:
                return []
            stmt = select(Output)
            for word in words:
                stmt = stmt.where(Output.search_text.like(_like_pattern(word), escape="\\"))
            return await self._rows(session, stmt, SEARCH_LIMIT)

    async def series_with_outputs(self, viewer: User) -> list[Series]:
        """Series that have at least one output (inactive series too: old outputs stay findable)."""
        async with self._db.read() as session:
            await _fresh(session, viewer)
            result = await session.execute(
                select(Series)
                .where(Series.id.in_(select(Output.series_id).where(Output.series_id.is_not(None))))
                .order_by(Series.id)
            )
            return list(result.scalars().all())

    async def detail(self, viewer: User, output_id: int) -> OutputDetail:
        async with self._db.read() as session:
            await _fresh(session, viewer)
            output = await session.get(Output, output_id)
            if output is None:
                raise NotFound("output")
            task = await session.get(Task, output.task_id)
            submission = await session.get(Submission, output.submission_id)
            owner = await users_repo.get_by_id(session, output.owner_id)
            if task is None or submission is None or owner is None:
                raise NotFound("output")
            series = await series_repo.get(session, output.series_id) if output.series_id else None
            item = await session.get(ContentItem, output.content_item_id) if output.content_item_id else None
            return OutputDetail(
                output=output, task=task, owner=owner, series=series, content_item=item,
                version=submission.version, attachments=list(submission.attachments or []),
                links=list(submission.links or []),
            )

    async def _rows(self, session: AsyncSession, stmt: Any, limit: int) -> list[OutputRow]:
        result = await session.execute(
            stmt.order_by(Output.approved_at.desc(), Output.id.desc()).limit(limit)
        )
        outputs = list(result.scalars().all())
        if not outputs:
            return []
        result = await session.execute(
            select(Task.id, Task.code).where(Task.id.in_({o.task_id for o in outputs}))
        )
        codes: dict[int, str] = {task_id: code for task_id, code in result.all()}
        people = await users_repo.get_many(session, {o.owner_id for o in outputs})
        return [OutputRow(output=o, task_code=codes.get(o.task_id, ""), owner=people[o.owner_id])
                for o in outputs]


async def _fresh(session: AsyncSession, viewer: User) -> User:
    fresh = await users_repo.get_by_id(session, viewer.id)
    if fresh is None or not fresh.can_use_bot:
        raise PermissionDenied("library")
    return fresh
