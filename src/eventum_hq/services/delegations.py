"""Temporary delegation of final approval (F7, handoff §4.4).

While a delegation is active (``starts_at <= now < ends_at`` and not revoked):
* in an L1_FINAL chain, the delegate's L1 approval is the final approval;
* in a FINAL chain, review goes to the delegate;
* ``Review.delegated = true`` is recorded.

Start and revoke notify both people right away. The "delegation ended" message
at ``ends_at`` needs the scheduler tick and arrives in M5.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from eventum_hq.core.db import Database
from eventum_hq.core.errors import AlreadyDecided, NotFound, PermissionDenied, ValidationFailed
from eventum_hq.core.timeutil import Clock, ensure_utc
from eventum_hq.models import Capability, Delegation, User
from eventum_hq.repositories import reviews as reviews_repo
from eventum_hq.repositories import users as users_repo
from eventum_hq.services import audit
from eventum_hq.services.notifications import enqueue
from eventum_hq.services.permissions import has_capability, require_capability, stored_capabilities

ENTITY = "delegation"
KIND_DELEGATION_STARTED = "delegation.started"
KIND_DELEGATION_REVOKED = "delegation.revoked"


@dataclass(frozen=True, slots=True)
class DelegationView:
    delegation: Delegation
    from_user: User
    to_user: User


async def active_delegate_id(session: AsyncSession, now: datetime) -> int | None:
    delegation = await reviews_repo.active_delegation(session, now)
    return delegation.to_user_id if delegation is not None else None


class DelegationService:
    def __init__(self, db: Database, clock: Clock) -> None:
        self._db = db
        self._clock = clock

    async def current(self) -> DelegationView | None:
        async with self._db.read() as session:
            delegation = await reviews_repo.active_delegation(session, self._clock.now())
            if delegation is None:
                return None
            people = await users_repo.get_many(session, {delegation.from_user_id, delegation.to_user_id})
            return DelegationView(delegation, people[delegation.from_user_id], people[delegation.to_user_id])

    async def is_active_delegate(self, user_id: int) -> bool:
        async with self._db.read() as session:
            return await active_delegate_id(session, self._clock.now()) == user_id

    async def candidates(self) -> list[User]:
        """People who may receive a delegation: active users with a stored REVIEW_L1."""
        async with self._db.read() as session:
            users = await users_repo.list_active(session)
        return [u for u in users if Capability.REVIEW_L1 in stored_capabilities(u)]

    async def create(self, actor: User, to_user_id: int, ends_at: datetime) -> Delegation:
        now = self._clock.now()
        ends_at = ensure_utc(ends_at)
        if ends_at <= now:
            raise ValidationFailed("delegation_end_past")
        async with self._db.transaction() as session:
            fresh = await users_repo.get_by_id(session, actor.id)
            if fresh is None or not fresh.can_use_bot:
                raise PermissionDenied("inactive")
            require_capability(fresh, Capability.DELEGATE)
            delegate = await users_repo.get_by_id(session, to_user_id)
            if (
                delegate is None
                or not delegate.can_use_bot
                or Capability.REVIEW_L1 not in stored_capabilities(delegate)
            ):
                raise ValidationFailed("delegate_invalid")
            if delegate.id == fresh.id:
                raise ValidationFailed("delegate_invalid")

            previous = await reviews_repo.active_delegation(session, now)
            if previous is not None:  # only one delegation at a time
                previous.revoked_at = now
                await audit.record(
                    session, actor_id=fresh.id, action="delegation.revoked", entity_type=ENTITY,
                    entity_id=previous.id, at=now, data={"reason": "replaced"},
                )

            delegation = Delegation(
                from_user_id=fresh.id, to_user_id=delegate.id, starts_at=now, ends_at=ends_at
            )
            session.add(delegation)
            await session.flush()
            await audit.record(
                session, actor_id=fresh.id, action="delegation.created", entity_type=ENTITY,
                entity_id=delegation.id, at=now,
                data={"to_user_id": delegate.id, "ends_at": ends_at.isoformat()},
            )
            await self._notify_both(session, delegation, fresh, delegate, KIND_DELEGATION_STARTED, now)
            return delegation

    async def revoke(self, actor: User, delegation_id: int) -> Delegation:
        now = self._clock.now()
        async with self._db.transaction() as session:
            fresh = await users_repo.get_by_id(session, actor.id)
            if fresh is None or not fresh.can_use_bot:
                raise PermissionDenied("inactive")
            delegation = await reviews_repo.get_delegation(session, delegation_id)
            if delegation is None:
                raise NotFound(f"delegation {delegation_id}")
            if not (has_capability(fresh, Capability.DELEGATE) or delegation.from_user_id == fresh.id):
                raise PermissionDenied("delegation.revoke")
            if delegation.revoked_at is not None or delegation.ends_at <= now:
                raise AlreadyDecided("ENDED")
            delegation.revoked_at = now
            await audit.record(
                session, actor_id=fresh.id, action="delegation.revoked", entity_type=ENTITY,
                entity_id=delegation.id, at=now, data={},
            )
            from_user = await users_repo.get_by_id(session, delegation.from_user_id)
            delegate = await users_repo.get_by_id(session, delegation.to_user_id)
            assert from_user is not None and delegate is not None
            await self._notify_both(session, delegation, from_user, delegate, KIND_DELEGATION_REVOKED, now)
            return delegation

    async def _notify_both(
        self, session: AsyncSession, delegation: Delegation, from_user: User, delegate: User,
        kind: str, now: datetime,
    ) -> None:
        payload = {
            "delegation_id": delegation.id,
            "from_name": from_user.full_name,
            "to_name": delegate.full_name,
            "ends_at": delegation.ends_at.isoformat(),
        }
        for person in (from_user, delegate):
            await enqueue(
                session, chat_id=person.telegram_id, kind=kind, payload=payload,
                dedupe_key=f"{kind}:{delegation.id}:{person.id}", now=now, urgent=True,
            )
