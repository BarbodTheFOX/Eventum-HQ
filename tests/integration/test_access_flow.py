"""Access-request flow end to end at the service level (handoff §3.3)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from eventum_hq.core.db import Database
from eventum_hq.core.errors import AlreadyDecided, NotFound, PermissionDenied
from eventum_hq.models import (
    AccessStatus,
    AuditEvent,
    Capability,
    Notification,
    NotificationStatus,
    Role,
    User,
)
from eventum_hq.services.users import (
    KIND_ACCESS_APPROVED,
    KIND_ACCESS_REJECTED,
    KIND_ACCESS_REQUEST,
    StartResult,
    UserService,
)
from tests.conftest import OWNER_TG, FakeClock, add_user

STRANGER_TG = 555


async def _all(db: Database, model):  # type: ignore[no-untyped-def]
    async with db.read() as s:
        return (await s.execute(select(model).order_by(model.id))).scalars().all()


async def _audit_actions(db: Database) -> list[str]:
    return [e.action for e in await _all(db, AuditEvent)]


# ---- owner bootstrap ----------------------------------------------------------


async def test_ensure_owner_creates_owner_once(db: Database, users: UserService) -> None:
    first = await users.ensure_owner()
    second = await users.ensure_owner()
    assert first.id == second.id
    assert first.role == Role.OWNER and first.can_use_bot
    assert await _audit_actions(db) == ["user.owner_bootstrapped"]


async def test_ensure_owner_promotes_existing_user(db: Database, users: UserService) -> None:
    await add_user(
        db, telegram_id=OWNER_TG, role=Role.MEMBER, is_active=False,
        access_status=AccessStatus.PENDING,
    )
    owner = await users.ensure_owner()
    assert owner.role == Role.OWNER and owner.can_use_bot
    assert await _audit_actions(db) == ["user.owner_bootstrapped"]


# ---- /start -----------------------------------------------------------------


async def test_owner_start_is_known_and_syncs_profile(db: Database, users: UserService, owner) -> None:
    out = await users.start(telegram_id=OWNER_TG, full_name="Farid", username="farid")
    assert out.result == StartResult.KNOWN
    assert out.user.full_name == "Farid"
    assert "user.profile_synced" in await _audit_actions(db)
    assert await _all(db, Notification) == []


async def test_unknown_start_creates_pending_user_and_notifies_owner(
    db: Database, users: UserService, owner: User
) -> None:
    out = await users.start(telegram_id=STRANGER_TG, full_name="Sina S", username="sina")
    assert out.result == StartResult.REQUEST_SENT

    user = out.user
    assert user.access_status == AccessStatus.PENDING
    assert user.is_active is False
    assert user.role == Role.MEMBER and user.capabilities == []
    assert await users.get_active_by_telegram_id(STRANGER_TG) is None

    rows = await _all(db, Notification)
    assert len(rows) == 1
    n = rows[0]
    assert n.chat_id == OWNER_TG
    assert n.kind == KIND_ACCESS_REQUEST
    assert n.urgent is True and n.status == NotificationStatus.PENDING
    assert n.payload == {
        "user_id": user.id, "telegram_id": STRANGER_TG, "full_name": "Sina S", "username": "sina",
    }
    assert "access.requested" in await _audit_actions(db)


async def test_at_most_one_request_per_24h(
    db: Database, users: UserService, owner, clock: FakeClock
) -> None:
    first = await users.start(telegram_id=STRANGER_TG, full_name="S", username=None)
    assert first.result == StartResult.REQUEST_SENT

    clock.advance(hours=23, minutes=59)
    again = await users.start(telegram_id=STRANGER_TG, full_name="S", username=None)
    assert again.result == StartResult.ALREADY_REQUESTED
    assert len(await _all(db, Notification)) == 1

    clock.advance(minutes=2)  # now > 24h after the first request
    later = await users.start(telegram_id=STRANGER_TG, full_name="S", username=None)
    assert later.result == StartResult.REQUEST_SENT
    assert len(await _all(db, Notification)) == 2
    assert (await _audit_actions(db)).count("access.requested") == 2


# ---- approve / reject -------------------------------------------------------


async def test_owner_approves_member(db: Database, users: UserService, owner: User) -> None:
    req = await users.start(telegram_id=STRANGER_TG, full_name="Sina", username="sina")
    approved = await users.approve_access(owner, req.user.id)

    assert approved.access_status == AccessStatus.APPROVED
    assert approved.is_active is True
    assert approved.role == Role.MEMBER
    active = await users.get_active_by_telegram_id(STRANGER_TG)
    assert active is not None and active.id == req.user.id

    events = [e for e in await _all(db, AuditEvent) if e.action == "access.approved"]
    assert len(events) == 1
    assert events[0].actor_id == owner.id
    assert events[0].data["before"]["access_status"] == "PENDING"
    assert events[0].data["after"]["access_status"] == "APPROVED"

    to_user = [n for n in await _all(db, Notification) if n.chat_id == STRANGER_TG]
    assert len(to_user) == 1 and to_user[0].kind == KIND_ACCESS_APPROVED and to_user[0].urgent

    # after approval /start shows the menu
    again = await users.start(telegram_id=STRANGER_TG, full_name="Sina", username="sina")
    assert again.result == StartResult.KNOWN


async def test_owner_rejects(db: Database, users: UserService, owner: User) -> None:
    req = await users.start(telegram_id=STRANGER_TG, full_name="Spam", username=None)
    rejected = await users.reject_access(owner, req.user.id)
    assert rejected.access_status == AccessStatus.REJECTED and rejected.is_active is False
    assert await users.get_active_by_telegram_id(STRANGER_TG) is None
    assert "access.rejected" in await _audit_actions(db)
    to_user = [n for n in await _all(db, Notification) if n.chat_id == STRANGER_TG]
    assert [n.kind for n in to_user] == [KIND_ACCESS_REJECTED]


async def test_second_decision_is_refused(db: Database, users: UserService, owner: User) -> None:
    req = await users.start(telegram_id=STRANGER_TG, full_name="S", username=None)
    await users.approve_access(owner, req.user.id)
    with pytest.raises(AlreadyDecided) as info:
        await users.reject_access(owner, req.user.id)
    assert info.value.current_status == "APPROVED"
    with pytest.raises(AlreadyDecided):
        await users.approve_access(owner, req.user.id)
    assert (await _audit_actions(db)).count("access.approved") == 1


@pytest.mark.parametrize(
    ("role", "caps"),
    [
        (Role.MANAGER, [Capability.CREATE_TASK, Capability.VIEW_ALL_TASKS]),
        (Role.MEMBER, [Capability.PUBLISH, Capability.SYSTEM_ADMIN]),
        (Role.MEMBER, [Capability.REVIEW_L1, Capability.CREATE_REEL]),
        (Role.MEMBER, []),
    ],
)
async def test_non_owner_cannot_decide(
    db: Database, users: UserService, owner, role: Role, caps: list[Capability]
) -> None:
    actor = await add_user(db, telegram_id=900, role=role, capabilities=caps)
    req = await users.start(telegram_id=STRANGER_TG, full_name="S", username=None)
    with pytest.raises(PermissionDenied):
        await users.approve_access(actor, req.user.id)
    with pytest.raises(PermissionDenied):
        await users.reject_access(actor, req.user.id)
    still = await users.get(req.user.id)
    assert still is not None and still.access_status == AccessStatus.PENDING


async def test_permission_is_rechecked_from_db(db: Database, users: UserService, owner: User) -> None:
    """A stale in-memory OWNER object must not be trusted once the DB says otherwise."""
    req = await users.start(telegram_id=STRANGER_TG, full_name="S", username=None)
    async with db.transaction() as s:
        row = await s.get(User, owner.id)
        assert row is not None
        row.is_active = False
    with pytest.raises(PermissionDenied):
        await users.approve_access(owner, req.user.id)


async def test_decision_on_missing_user(users: UserService, owner: User) -> None:
    with pytest.raises(NotFound):
        await users.approve_access(owner, 99999)


async def test_rejected_user_can_request_again_after_24h(
    db: Database, users: UserService, owner: User, clock: FakeClock
) -> None:
    req = await users.start(telegram_id=STRANGER_TG, full_name="S", username=None)
    await users.reject_access(owner, req.user.id)
    clock.advance(hours=1)
    assert (await users.start(telegram_id=STRANGER_TG, full_name="S", username=None)).result == (
        StartResult.ALREADY_REQUESTED
    )
    clock.advance(hours=24)
    again = await users.start(telegram_id=STRANGER_TG, full_name="S", username=None)
    assert again.result == StartResult.REQUEST_SENT
    assert again.user.access_status == AccessStatus.PENDING
    await users.approve_access(owner, req.user.id)
    assert await users.get_active_by_telegram_id(STRANGER_TG) is not None
