"""Clock-driven jobs of the tick that only queue outbox rows (handoff §5.5, §5.6, §6.4, §6.5).

Every job is idempotent through ``job_runs`` (one run per day/week key), so a
restart or a second tick in the same minute never sends twice. If the bot was
down at the planned time, the job runs at the first tick after it — the same day.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from eventum_hq.core.db import Database
from eventum_hq.core.jalali import tehran_today
from eventum_hq.core.timeutil import Clock, weekday_sat0
from eventum_hq.models import Capability, User
from eventum_hq.repositories import jobs as jobs_repo
from eventum_hq.repositories import users as users_repo
from eventum_hq.services import schedule
from eventum_hq.services.backup import BackupService
from eventum_hq.services.notifications import enqueue
from eventum_hq.services.permissions import stored_capabilities
from eventum_hq.services.reports import ReportService, can_receive_report

log = logging.getLogger(__name__)

KIND_HEARTBEAT = "system.heartbeat"
KIND_BACKUP_WEEKLY = "system.backup_weekly"
KIND_BACKUP_TOO_BIG = "system.backup_too_big"
KIND_DAILY_PLAN = "group.daily_plan"
KIND_WEEKLY_SUMMARY = "group.weekly_summary"
KIND_SATURDAY_REPORT = "report.saturday"

HEARTBEAT_GAP = timedelta(minutes=5)
SATURDAY = 0


async def system_admins(session: AsyncSession) -> list[User]:
    return [u for u in await users_repo.list_active(session)
            if Capability.SYSTEM_ADMIN in stored_capabilities(u)]


class PeriodicService:
    def __init__(
        self, db: Database, clock: Clock, reports: ReportService, backups: BackupService,
        team_group_id: int | None,
    ) -> None:
        self._db = db
        self._clock = clock
        self._reports = reports
        self._backups = backups
        self._group = team_group_id

    async def heartbeat(self) -> timedelta | None:
        """Record this tick; if the previous one is older than 5 minutes, alert SYSTEM_ADMINs."""
        now = self._clock.now()
        async with self._db.transaction() as session:
            previous = await jobs_repo.touch(session, jobs_repo.HEARTBEAT_JOB, jobs_repo.HEARTBEAT_KEY, now)
            if previous is None or now - previous <= HEARTBEAT_GAP:
                return None
            gap = now - previous
            for admin in await system_admins(session):
                await enqueue(
                    session, chat_id=admin.telegram_id, kind=KIND_HEARTBEAT,
                    payload={"user_id": admin.id, "minutes": int(gap.total_seconds() // 60),
                             "since": previous.isoformat()},
                    dedupe_key=f"{KIND_HEARTBEAT}:{admin.id}:{now.isoformat()}", now=now, urgent=True,
                )
            log.warning("tick was silent for %s", gap)
            return gap

    async def group_messages(self) -> list[str]:
        """«برنامهٔ امروز» and «جمع‌بندی هفتگی» in the team group (only if TEAM_GROUP_ID is set)."""
        if self._group is None:
            return []
        now = self._clock.now()
        day = schedule.local_date_key(now)
        queued: list[str] = []
        async with self._db.read() as session:
            cfg = await schedule.load(session)
        plan_due = weekday_sat0(now) in cfg.digest_days and schedule.is_due_today(now, None, cfg.digest_time)
        plan_empty = (await self._reports.daily_plan()).empty if plan_due else True
        async with self._db.transaction() as session:
            if plan_due and await jobs_repo.claim(session, KIND_DAILY_PLAN, day, now):
                if not plan_empty:  # nothing planned today → no message (§5.5)
                    await self._group_row(session, KIND_DAILY_PLAN, day, now)
                    queued.append(KIND_DAILY_PLAN)
            if (schedule.is_due_today(now, cfg.summary_day, cfg.summary_time)
                    and await jobs_repo.claim(session, KIND_WEEKLY_SUMMARY, day, now)):
                await self._group_row(session, KIND_WEEKLY_SUMMARY, day, now)
                queued.append(KIND_WEEKLY_SUMMARY)
        return queued

    async def saturday_report(self) -> int:
        """Saturday 09:00: the report to the OWNER and every stored RECEIVE_WEEKLY_REPORT."""
        now = self._clock.now()
        day = schedule.local_date_key(now)
        async with self._db.transaction() as session:
            cfg = await schedule.load(session)
            if not schedule.is_due_today(now, SATURDAY, cfg.report_time):
                return 0
            if not await jobs_repo.claim(session, KIND_SATURDAY_REPORT, day, now):
                return 0
            count = 0
            for user in await users_repo.list_active(session):
                if not can_receive_report(user):
                    continue
                row = await enqueue(
                    session, chat_id=user.telegram_id, kind=KIND_SATURDAY_REPORT,
                    payload={"user_id": user.id}, dedupe_key=f"{KIND_SATURDAY_REPORT}:{user.id}:{day}", now=now,
                )
                count += row is not None
        return count

    async def backups(self) -> list[str]:
        """Daily copy at 04:00; on Friday 04:30 the gzipped copy goes to SYSTEM_ADMINs."""
        if not self._backups.enabled:
            return []
        now = self._clock.now()
        today = schedule.local_date_key(now)
        done: list[str] = []
        async with self._db.transaction() as session:
            cfg = await schedule.load(session)
            daily = (schedule.is_due_today(now, None, cfg.backup_daily_time)
                     and await jobs_repo.claim(session, "backup.daily", today, now))
            weekly = (schedule.is_due_today(now, cfg.backup_weekly_day, cfg.backup_weekly_time)
                      and await jobs_repo.claim(session, "backup.weekly", today, now))
        local_day = tehran_today(now)
        if daily:
            path = await self._backups.daily(local_day)
            log.info("daily backup written: %s", path)
            done.append("daily")
        if weekly:
            packed = await self._backups.weekly(local_day)
            if packed is not None:
                async with self._db.transaction() as session:
                    kind = KIND_BACKUP_WEEKLY if packed.sendable else KIND_BACKUP_TOO_BIG
                    for admin in await system_admins(session):
                        await enqueue(
                            session, chat_id=admin.telegram_id, kind=kind,
                            payload={"user_id": admin.id, "path": str(packed.path), "size": packed.size},
                            dedupe_key=f"{kind}:{admin.id}:{today}", now=now,
                        )
                done.append("weekly")
        return done

    async def _group_row(self, session: AsyncSession, kind: str, day: str, now: datetime) -> None:
        assert self._group is not None
        await enqueue(session, chat_id=self._group, kind=kind, payload={"day": day},
                      dedupe_key=f"{kind}:{day}", now=now)
