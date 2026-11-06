"""Users and the access-request flow (handoff §3.3, F1).

Flow:
1. Unknown user sends /start  → ``start()`` creates a PENDING user, writes an
   audit event and queues one access-request card for each OWNER
   (at most once per 24 hours per user).
2. OWNER presses approve/reject → ``approve_access()`` / ``reject_access()``
   re-checks permission from the DB, changes status, audits, and queues a
   message for the applicant.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from eventum_hq.core.db import Database
from eventum_hq.core.errors import AlreadyDecided, NotFound, PermissionDenied
from eventum_hq.core.timeutil import Clock
from eventum_hq.models import AccessStatus, Capability, Role, User
from eventum_hq.repositories import audit as audit_repo
from eventum_hq.repositories import users as users_repo
from eventum_hq.services import audit
from eventum_hq.services.notifications import enqueue
from eventum_hq.services.permissions import require_capability

ACCESS_REQUEST_INTERVAL = timedelta(hours=24)
ENTITY = "user"

# Outbox kinds (rendered by bot/outbox.py)
KIND_ACCESS_REQUEST = "access.request"
KIND_ACCESS_APPROVED = "access.approved"
KIND_ACCESS_REJECTED = "access.rejected"


class StartResult(StrEnum):
    KNOWN = "KNOWN"  # approved + active: show the menu
    REQUEST_SENT = "REQUEST_SENT"  # a new request was sent to the OWNER
    ALREADY_REQUESTED = "ALREADY_REQUESTED"  # a request was sent in the last 24h


@dataclass(frozen=True, slots=True)
class StartOutcome:
    result: StartResult
    user: User


class UserService:
    def __init__(self, db: Database, clock: Clock, owner_telegram_id: int) -> None:
        self._db = db
        self._clock = clock
        self._owner_telegram_id = owner_telegram_id

    # ---- reads -------------------------------------------------------------

    async def get_active_by_telegram_id(self, telegram_id: int) -> User | None:
        """The user if they may use the bot (approved and active), else ``None``."""
        async with self._db.read() as session:
            user = await users_repo.get_by_telegram_id(session, telegram_id)
        return user if user is not None and user.can_use_bot else None

    async def get(self, user_id: int) -> User | None:
        async with self._db.read() as session:
            return await users_repo.get_by_id(session, user_id)

    # ---- bootstrap ---------------------------------------------------------

    async def ensure_owner(self) -> User:
        """Make sure ``OWNER_TELEGRAM_ID`` exists as an active, approved OWNER."""
        now = self._clock.now()
        async with self._db.transaction() as session:
            user = await users_repo.get_by_telegram_id(session, self._owner_telegram_id)
            if user is None:
                user = User(
                    telegram_id=self._owner_telegram_id,
                    full_name="",
                    role=Role.OWNER,
                    capabilities=[],
                    is_active=True,
                    access_status=AccessStatus.APPROVED,
                )
                session.add(user)
                await session.flush()
                await audit.record(
                    session,
                    actor_id=None,
                    action="user.owner_bootstrapped",
                    entity_type=ENTITY,
                    entity_id=user.id,
                    at=now,
                    data={"telegram_id": self._owner_telegram_id},
                )
                return user

            if user.role == Role.OWNER and user.can_use_bot:
                return user

            before = _snapshot(user)
            user.role = Role.OWNER
            user.is_active = True
            user.deactivated_at = None
            user.access_status = AccessStatus.APPROVED
            await audit.record(
                session,
                actor_id=None,
                action="user.owner_bootstrapped",
                entity_type=ENTITY,
                entity_id=user.id,
                at=now,
                data={"before": before, "after": _snapshot(user)},
            )
            return user

    # ---- /start ------------------------------------------------------------

    async def start(self, *, telegram_id: int, full_name: str, username: str | None) -> StartOutcome:
        now = self._clock.now()
        full_name = (full_name or "").strip()
        async with self._db.transaction() as session:
            user = await users_repo.get_by_telegram_id(session, telegram_id)

            if user is not None and user.can_use_bot:
                await self._sync_profile(session, user, full_name, username)
                return StartOutcome(StartResult.KNOWN, user)

            if user is None:
                user = User(
                    telegram_id=telegram_id,
                    full_name=full_name,
                    username=username,
                    role=Role.MEMBER,
                    capabilities=[],
                    is_active=False,
                    access_status=AccessStatus.PENDING,
                )
                session.add(user)
                await session.flush()
            else:
                await self._sync_profile(session, user, full_name, username)

            last = await audit_repo.last_event(
                session, entity_type=ENTITY, entity_id=user.id, action="access.requested"
            )
            if last is not None and now - last.at < ACCESS_REQUEST_INTERVAL:
                return StartOutcome(StartResult.ALREADY_REQUESTED, user)

            previous_status = user.access_status
            user.access_status = AccessStatus.PENDING
            await audit.record(
                session,
                actor_id=None,
                action="access.requested",
                entity_type=ENTITY,
                entity_id=user.id,
                at=now,
                data={
                    "telegram_id": telegram_id,
                    "full_name": full_name,
                    "username": username,
                    "previous_status": str(previous_status),
                },
            )
            payload = {
                "user_id": user.id,
                "telegram_id": telegram_id,
                "full_name": full_name,
                "username": username,
            }
            for owner in await users_repo.list_active_owners(session):
                await enqueue(
                    session,
                    chat_id=owner.telegram_id,
                    kind=KIND_ACCESS_REQUEST,
                    payload=payload,
                    dedupe_key=f"{KIND_ACCESS_REQUEST}:{user.id}:{owner.id}:{now.isoformat()}",
                    now=now,
                    urgent=True,
                )
            return StartOutcome(StartResult.REQUEST_SENT, user)

    # ---- decisions ---------------------------------------------------------

    async def approve_access(self, actor: User, target_user_id: int) -> User:
        return await self._decide(actor, target_user_id, approve=True)

    async def reject_access(self, actor: User, target_user_id: int) -> User:
        return await self._decide(actor, target_user_id, approve=False)

    async def _decide(self, actor: User, target_user_id: int, *, approve: bool) -> User:
        now = self._clock.now()
        async with self._db.transaction() as session:
            # Re-read the actor: never trust what the button/caller says.
            fresh_actor = await users_repo.get_by_id(session, actor.id)
            if fresh_actor is None:
                raise PermissionDenied(Capability.MANAGE_USERS.value)
            require_capability(fresh_actor, Capability.MANAGE_USERS)

            target = await users_repo.get_by_id(session, target_user_id)
            if target is None:
                raise NotFound(f"user {target_user_id}")
            if target.access_status != AccessStatus.PENDING:
                raise AlreadyDecided(str(target.access_status))

            before = _snapshot(target)
            if approve:
                target.access_status = AccessStatus.APPROVED
                target.is_active = True
                target.deactivated_at = None
                action, kind = "access.approved", KIND_ACCESS_APPROVED
            else:
                target.access_status = AccessStatus.REJECTED
                target.is_active = False
                action, kind = "access.rejected", KIND_ACCESS_REJECTED

            await audit.record(
                session,
                actor_id=fresh_actor.id,
                action=action,
                entity_type=ENTITY,
                entity_id=target.id,
                at=now,
                data={"before": before, "after": _snapshot(target)},
            )
            await enqueue(
                session,
                chat_id=target.telegram_id,
                kind=kind,
                payload={"user_id": target.id},
                dedupe_key=f"{kind}:{target.id}:{now.isoformat()}",
                now=now,
                urgent=True,
            )
            return target

    # ---- helpers -----------------------------------------------------------

    async def _sync_profile(
        self, session: AsyncSession, user: User, full_name: str, username: str | None
    ) -> None:
        """Keep name/username in sync with Telegram (audited when changed)."""
        changes: dict[str, dict[str, str | None]] = {}
        if full_name and full_name != user.full_name:
            changes["full_name"] = {"before": user.full_name, "after": full_name}
            user.full_name = full_name
        if username != user.username:
            changes["username"] = {"before": user.username, "after": username}
            user.username = username
        if changes:
            await audit.record(
                session,
                actor_id=user.id if user.can_use_bot else None,
                action="user.profile_synced",
                entity_type=ENTITY,
                entity_id=user.id,
                at=self._clock.now(),
                data=changes,
            )


def _snapshot(user: User) -> dict[str, object]:
    return {
        "role": str(user.role),
        "is_active": user.is_active,
        "access_status": str(user.access_status),
        "capabilities": list(user.capabilities or []),
    }
