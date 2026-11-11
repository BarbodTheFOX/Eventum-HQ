"""The 60-second tick (handoff §6.1, §6.2). The database is the only source of truth,
so nothing is lost across restarts: every job checks ``job_runs`` / dedupe keys.

Order inside one tick: heartbeat → recurrences → deadlines → group messages →
Saturday report → backups → deliver the outbox. One failing job is logged and
never stops the others.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from eventum_hq.services.deadlines import DeadlineService
from eventum_hq.services.periodic import PeriodicService
from eventum_hq.services.recurrences import RecurrenceService

log = logging.getLogger(__name__)

TICK_SECONDS = 60


class Deliverer(Protocol):
    async def deliver_due(self) -> int: ...


class Scheduler:
    def __init__(
        self,
        *,
        periodic: PeriodicService,
        recurrences: RecurrenceService,
        deadlines: DeadlineService,
        outbox: Deliverer,
        interval: float = TICK_SECONDS,
    ) -> None:
        self._periodic = periodic
        self._recurrences = recurrences
        self._deadlines = deadlines
        self._outbox = outbox
        self._interval = interval

    async def tick(self) -> dict[str, Any]:
        results: dict[str, Any] = {}
        jobs: list[tuple[str, Callable[[], Awaitable[Any]]]] = [
            ("heartbeat", self._periodic.heartbeat),
            ("recurrences", self._recurrences.generate_due),
            ("deadlines", self._deadlines.run),
            ("group", self._periodic.group_messages),
            ("report", self._periodic.saturday_report),
            ("backups", self._periodic.backups),
            ("outbox", self._outbox.deliver_due),
        ]
        for name, job in jobs:
            try:
                results[name] = await job()
            except Exception:
                log.exception("tick job %s failed", name)
                results[name] = None
        return results

    async def run_forever(self) -> None:
        log.info("scheduler started (every %ss)", self._interval)
        while True:
            await self.tick()
            await asyncio.sleep(self._interval)
