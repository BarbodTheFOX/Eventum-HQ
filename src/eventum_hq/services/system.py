"""Operations: ``/health``, ``/backup`` and error alerts (handoff §6.4, §6.5).

* ``/health`` and ``/backup`` are for ``SYSTEM_ADMIN`` holders (the OWNER implicitly).
* Errors are reported to every stored ``SYSTEM_ADMIN`` through the outbox, at most
  one message per error type per 10 minutes: the dedupe key carries a 10-minute
  bucket, so the database does the rate limiting and it survives restarts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from eventum_hq.core.db import Database
from eventum_hq.core.errors import PermissionDenied, ValidationFailed
from eventum_hq.core.jalali import tehran_today
from eventum_hq.core.timeutil import Clock
from eventum_hq.models import Capability, User
from eventum_hq.repositories import jobs as jobs_repo
from eventum_hq.repositories import notifications as notifications_repo
from eventum_hq.repositories import users as users_repo
from eventum_hq.services import audit
from eventum_hq.services.backup import BackupService, WeeklyBackup
from eventum_hq.services.notifications import enqueue
from eventum_hq.services.periodic import HEARTBEAT_GAP, system_admins
from eventum_hq.services.permissions import require_capability

log = logging.getLogger(__name__)

KIND_SYSTEM_ERROR = "system.error"
ERROR_WINDOW = timedelta(minutes=10)
ERROR_TEXT_MAX = 300


@dataclass(frozen=True, slots=True)
class HealthReport:
    now: datetime
    uptime: timedelta
    last_tick: datetime | None
    tick_ok: bool
    db_size: int | None
    last_backup: datetime | None
    last_backup_name: str | None
    outbox_pending: int
    outbox_failed_24h: int
    active_users: int


def error_bucket(now: datetime) -> int:
    return int(now.timestamp() // ERROR_WINDOW.total_seconds())


class SystemService:
    def __init__(self, db: Database, clock: Clock, backups: BackupService, started_at: datetime | None = None,
                 secrets: list[str] | None = None) -> None:
        self._db = db
        self._secrets = [s for s in (secrets or []) if s]
        self._clock = clock
        self._backups = backups
        self._started = started_at or clock.now()

    async def _require_admin(self, actor: User) -> User:
        async with self._db.read() as session:
            fresh = await users_repo.get_by_id(session, actor.id)
        if fresh is None or not fresh.can_use_bot:
            raise PermissionDenied("inactive")
        require_capability(fresh, Capability.SYSTEM_ADMIN)
        return fresh

    async def health(self, actor: User) -> HealthReport:
        await self._require_admin(actor)
        now = self._clock.now()
        async with self._db.read() as session:
            tick = await jobs_repo.get(session, jobs_repo.HEARTBEAT_JOB, jobs_repo.HEARTBEAT_KEY)
            pending = await notifications_repo.count_pending(session)
            failed = await notifications_repo.count_failed_since(session, now - timedelta(hours=24))
            active = len(await users_repo.list_active(session))
        last_tick = tick.ran_at if tick is not None else None
        latest = self._backups.latest()
        return HealthReport(
            now=now,
            uptime=now - self._started,
            last_tick=last_tick,
            tick_ok=last_tick is not None and now - last_tick <= HEARTBEAT_GAP,
            db_size=self._backups.database_size(),
            last_backup=datetime.fromtimestamp(latest[1], tz=UTC) if latest else None,
            last_backup_name=latest[0].name if latest else None,
            outbox_pending=pending,
            outbox_failed_24h=failed,
            active_users=active,
        )

    async def backup_now(self, actor: User) -> WeeklyBackup:
        """``/backup``: a fresh copy now, gzipped, for the bot to send to the admin."""
        fresh = await self._require_admin(actor)
        if not self._backups.enabled:
            raise ValidationFailed("backup_disabled")
        now = self._clock.now()
        day = tehran_today(now)
        await self._backups.daily(day)
        packed = await self._backups.weekly(day)
        if packed is None:
            raise ValidationFailed("backup_disabled")
        async with self._db.transaction() as session:
            await audit.record(session, actor_id=fresh.id, action="system.backup_manual", entity_type="system",
                               entity_id=0, at=now, data={"file": packed.path.name, "size": packed.size})
        return packed

    async def report_error(self, kind: str, where: str, message: str) -> int:
        """Queue an error alert for SYSTEM_ADMINs (rate-limited). Never raises."""
        try:
            for secret in self._secrets:  # never send the bot token in an alert
                message = message.replace(secret, "***")
            now = self._clock.now()
            bucket = error_bucket(now)
            queued = 0
            async with self._db.transaction() as session:
                for admin in await system_admins(session):
                    row = await enqueue(
                        session, chat_id=admin.telegram_id, kind=KIND_SYSTEM_ERROR,
                        payload={"user_id": admin.id, "error": kind[:100], "where": where[:100],
                                 "message": message[:ERROR_TEXT_MAX]},
                        dedupe_key=f"{KIND_SYSTEM_ERROR}:{kind[:100]}:{admin.id}:{bucket}", now=now, urgent=True,
                    )
                    queued += row is not None
            return queued
        except Exception:
            log.exception("could not queue the error alert")
            return 0
