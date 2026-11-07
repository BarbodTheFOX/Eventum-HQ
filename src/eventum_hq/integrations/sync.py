"""Codecks readiness (handoff §6.6).

Services call these hooks *after* a successful commit. v0 ships ``NoopSync``;
a real Codecks adapter can implement ``TaskSyncPort`` later without touching
business logic.
"""

from __future__ import annotations

from typing import Protocol


class TaskSyncPort(Protocol):
    async def on_task_created(self, task_id: int) -> None: ...

    async def on_task_updated(self, task_id: int) -> None: ...

    async def on_task_status_changed(self, task_id: int, old: str, new: str) -> None: ...


class NoopSync:
    async def on_task_created(self, task_id: int) -> None:
        return None

    async def on_task_updated(self, task_id: int) -> None:
        return None

    async def on_task_status_changed(self, task_id: int, old: str, new: str) -> None:
        return None
