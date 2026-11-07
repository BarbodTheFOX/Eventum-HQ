"""Users and the access-request flow (handoff v1.1 §3.3, F1).

Flow:
1. Unknown user sends /start → ``start()`` returns CHOOSE_ROLE (or
   ALREADY_REQUESTED if a request was sent in the last 24 hours).
2. User picks a role → ``request_access()`` creates/updates a PENDING user with
   that role, writes an audit event and queues an access-request card for the
   OWNER (at most once per 24 hours per user).
3. OWNER approves (with the requested role or another one) or rejects →
   ``approve_access()`` / ``reject_access()`` re-checks permission from the DB,
   stores the role and its default capabilities, audits, and queues a message
   for the applicant.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from eventum_hq.core.db import Database
from eventum_hq.core.errors import AlreadyDecided, InvalidRole, NotFound, PermissionDenied
from eventum_hq.core.timeutil import Clock
from eventum_hq.models import AccessStatus, Role, User
from eventum_hq.repositories import audit as audit_repo
from eventum_hq.repositories import users as users_repo
from eventum_hq.services import audit
from eventum_hq.services.notifications import enqueue
from eventum_hq.services.permissions import SELECTABLE_ROLES, default_capabilities, is_owner

ACCESS_REQUEST_INTERVAL = timedelta(hours=24)
ENTITY = "user"

# Outbox kinds (rendered by bot/outbox.py)
KIND_ACCESS_REQUEST = "access.request"
KIND_ACCESS_APPROVED = "access.approved"
KIND_ACCESS_REJECTED = "access.rejected"


class StartResult(StrEnum):
    KNOWN = "KNOWN"  # approved + active: show the menu
    CHOOSE_ROLE = "CHOOSE_ROLE"  # unknown: ask which role they have in the team
    ALREADY_REQUESTED = "ALREADY_REQUESTED"  # a request was sent in the last 24h


class RequestResult(StrEnum):
    REQUEST_SENT = "REQUEST_SENT"
    ALREADY_REQUESTED = "ALREADY_REQUESTED"
    ALREADY_MEMBER = "ALREADY_MEMBER"


@dataclass(frozen=True, slots=True)
class StartOutcome:
    result: StartResult
    user: User | None


@dataclass(frozen=True, slots=True)
class RequestOutcome:
    result: RequestResult
    user: User


def parse_selectable_role(value: str | Role | None) -> Role:
    """Validate a role coming from a button. Never trust callback data."""
    try:
        role = Role(value) if value is not None else None
    except ValueError:
        role = None
    if role is None or role not in SELECTABLE_ROLES:
        raise InvalidRole(str(value))
    return role


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
                    capabilities=default_capabilities(Role.OWNER),
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
            user.capabilities = default_capabilities(Role.OWNER)
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
            if user is None:
                return StartOutcome(StartResult.CHOOSE_ROLE, None)

            await self._sync_profile(session, user, full_name, username)
            if user.can_use_bot:
                return StartOutcome(StartResult.KNOWN, user)
            if await self._requested_recently(session, user, now):
                return StartOutcome(StartResult.ALREADY_REQUESTED, user)
            return StartOutcome(StartResult.CHOOSE_ROLE, user)

    # ---- access request ----------------------------------------------------

    async def request_access(
        self, *, telegram_id: int, full_name: str, username: str | None, role: str | Role
    ) -> RequestOutcome:
        requested_role = parse_selectable_role(role)
        now = self._clock.now()
        full_name = (full_name or "").strip()
        async with self._db.transaction() as session:
            user = await users_repo.get_by_telegram_id(session, telegram_id)

            if user is not None:
                await self._sync_profile(session, user, full_name, username)
                if user.can_use_bot:
                    return RequestOutcome(RequestResult.ALREADY_MEMBER, user)
                if await self._requested_recently(session, user, now):
                    return RequestOutcome(RequestResult.ALREADY_REQUESTED, user)
            else:
                user = User(
                    telegram_id=telegram_id,
                    full_name=full_name,
                    username=username,
                    role=requested_role,
                    capabilities=[],
                    is_active=False,
                    access_status=AccessStatus.PENDING,
                )
                session.add(user)
                await session.flush()

            previous_status = user.access_status
            user.role = requested_role  # while PENDING, role = requested role
            user.capabilities = []
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
                    "requested_role": str(requested_role),
                    "previous_status": str(previous_status),
                },
            )
            payload = {
                "user_id": user.id,
                "telegram_id": telegram_id,
                "full_name": full_name,
                "username": username,
                "requested_role": str(requested_role),
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
            return RequestOutcome(RequestResult.REQUEST_SENT, user)

    # ---- decisions ---------------------------------------------------------

    async def approve_access(
        self, actor: User, target_user_id: int, role: str | Role | None = None
    ) -> User:
        """Approve with ``role``, or with the role the user asked for if ``None``."""
        return await self._decide(actor, target_user_id, approve=True, role=role)

    async def reject_access(self, actor: User, target_user_id: int) -> User:
        return await self._decide(actor, target_user_id, approve=False, role=None)

    async def pending_request(self, actor: User, target_user_id: int) -> User:
        """Load a PENDING applicant for the OWNER's card (permission-checked)."""
        async with self._db.read() as session:
            fresh_actor = await users_repo.get_by_id(session, actor.id)
            if fresh_actor is None or not is_owner(fresh_actor):
                raise PermissionDenied("access.decide")
            target = await users_repo.get_by_id(session, target_user_id)
            if target is None:
                raise NotFound(f"user {target_user_id}")
            if target.access_status != AccessStatus.PENDING:
                raise AlreadyDecided(str(target.access_status))
            return target

    async def _decide(
        self, actor: User, target_user_id: int, *, approve: bool, role: str | Role | None
    ) -> User:
        now = self._clock.now()
        async with self._db.transaction() as session:
            # Re-read the actor: never trust what the button/caller says.
            fresh_actor = await users_repo.get_by_id(session, actor.id)
            if fresh_actor is None or not is_owner(fresh_actor):
                raise PermissionDenied("access.decide")

            target = await users_repo.get_by_id(session, target_user_id)
            if target is None:
                raise NotFound(f"user {target_user_id}")
            if target.access_status != AccessStatus.PENDING:
                raise AlreadyDecided(str(target.access_status))

            requested_role = target.role
            before = _snapshot(target)
            if approve:
                final_role = parse_selectable_role(role if role is not None else requested_role)
                target.role = final_role
                target.capabilities = default_capabilities(final_role)
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
                data={
                    "requested_role": str(requested_role),
                    "before": before,
                    "after": _snapshot(target),
                },
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

    async def _requested_recently(self, session: AsyncSession, user: User, now) -> bool:  # type: ignore[no-untyped-def]
        last = await audit_repo.last_event(
            session, entity_type=ENTITY, entity_id=user.id, action="access.requested"
        )
        return last is not None and now - last.at < ACCESS_REQUEST_INTERVAL

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
