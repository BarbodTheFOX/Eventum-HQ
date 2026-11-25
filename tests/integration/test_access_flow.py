"""Access-request flow with role selection, at the service level (handoff v1.1 §3.3)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from eventum_hq.core.db import Database
from eventum_hq.core.errors import AlreadyDecided, InvalidRole, NotFound, PermissionDenied
from eventum_hq.models import (
    AccessStatus,
    AuditEvent,
    Capability,
    Notification,
    NotificationStatus,
    Role,
    User,
)
from eventum_hq.services.permissions import ROLE_DEFAULT_CAPABILITIES, default_capabilities
from eventum_hq.services.users import (
    KIND_ACCESS_APPROVED,
    KIND_ACCESS_REJECTED,
    KIND_ACCESS_REQUEST,
    RequestResult,
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


async def _request(users: UserService, role: str | Role = Role.EDITOR, tg: int = STRANGER_TG):  # type: ignore[no-untyped-def]
    return await users.request_access(telegram_id=tg, full_name="Sina S", username="sina", role=role)


# ---- owner bootstrap ----------------------------------------------------------


async def test_ensure_owner_creates_owner_once(db: Database, users: UserService) -> None:
    first = await users.ensure_owner()
    second = await users.ensure_owner()
    assert first.id == second.id
    assert first.role == Role.OWNER and first.can_use_bot
    assert first.capabilities == default_capabilities(Role.OWNER)
    assert await _audit_actions(db) == ["user.owner_bootstrapped"]


async def test_existing_owner_gets_management_without_final_approval(db: Database, users: UserService) -> None:
    await add_user(db, telegram_id=OWNER_TG, role=Role.OWNER,
                   capabilities=[Capability.PUBLISH, Capability.SYSTEM_ADMIN])
    owner = await users.ensure_owner()
    assert set(default_capabilities(Role.OWNER)).issubset(owner.capabilities)
    assert Capability.APPROVE_FINAL.value not in owner.capabilities
    await users.ensure_owner()
    assert await _audit_actions(db) == ["user.owner_management_enabled"]


async def test_ensure_owner_promotes_existing_user(db: Database, users: UserService) -> None:
    await add_user(
        db, telegram_id=OWNER_TG, role=Role.EDITOR, is_active=False,
        access_status=AccessStatus.PENDING,
    )
    owner = await users.ensure_owner()
    assert owner.role == Role.OWNER and owner.can_use_bot
    assert await _audit_actions(db) == ["user.owner_bootstrapped"]


# ---- /start -----------------------------------------------------------------


async def test_owner_start_is_known_and_syncs_profile(db: Database, users: UserService, owner) -> None:
    out = await users.start(telegram_id=OWNER_TG, full_name="Barbod", username="barbod")
    assert out.result == StartResult.KNOWN
    assert out.user is not None and out.user.full_name == "Barbod"
    assert "user.profile_synced" in await _audit_actions(db)
    assert await _all(db, Notification) == []


async def test_unknown_start_asks_for_role_and_writes_nothing(
    db: Database, users: UserService, owner
) -> None:
    out = await users.start(telegram_id=STRANGER_TG, full_name="S", username=None)
    assert out.result == StartResult.CHOOSE_ROLE and out.user is None
    assert len(await _all(db, User)) == 1  # only the owner
    assert await _all(db, Notification) == []


# ---- request -----------------------------------------------------------------


@pytest.mark.parametrize("role", [r for r in Role if r != Role.OWNER])
async def test_request_with_role_notifies_owner(
    db: Database, users: UserService, owner: User, role: Role
) -> None:
    out = await _request(users, role.value)
    assert out.result == RequestResult.REQUEST_SENT

    user = out.user
    assert user.access_status == AccessStatus.PENDING and user.is_active is False
    assert user.role == role and user.capabilities == []
    assert await users.get_active_by_telegram_id(STRANGER_TG) is None

    rows = await _all(db, Notification)
    assert len(rows) == 1
    n = rows[0]
    assert n.chat_id == OWNER_TG and n.kind == KIND_ACCESS_REQUEST
    assert n.urgent is True and n.status == NotificationStatus.PENDING
    assert n.payload == {
        "user_id": user.id, "telegram_id": STRANGER_TG, "full_name": "Sina S",
        "username": "sina", "requested_role": role.value,
    }
    event = [e for e in await _all(db, AuditEvent) if e.action == "access.requested"][0]
    assert event.data["requested_role"] == role.value


@pytest.mark.parametrize("bad", ["OWNER", "MEMBER", "ADMIN", "", "editor"])
async def test_owner_or_unknown_role_cannot_be_requested(
    db: Database, users: UserService, owner, bad: str
) -> None:
    with pytest.raises(InvalidRole):
        await _request(users, bad)
    assert len(await _all(db, User)) == 1
    assert await _all(db, Notification) == []


async def test_at_most_one_request_per_24h(
    db: Database, users: UserService, owner, clock: FakeClock
) -> None:
    assert (await _request(users)).result == RequestResult.REQUEST_SENT

    clock.advance(hours=23, minutes=59)
    start = await users.start(telegram_id=STRANGER_TG, full_name="S", username=None)
    assert start.result == StartResult.ALREADY_REQUESTED
    assert (await _request(users, Role.DIRECTOR)).result == RequestResult.ALREADY_REQUESTED
    assert len(await _all(db, Notification)) == 1

    clock.advance(minutes=2)  # now > 24h after the first request
    start = await users.start(telegram_id=STRANGER_TG, full_name="S", username=None)
    assert start.result == StartResult.CHOOSE_ROLE
    later = await _request(users, Role.DESIGNER)
    assert later.result == RequestResult.REQUEST_SENT
    assert later.user.role == Role.DESIGNER
    assert len(await _all(db, Notification)) == 2


async def test_member_pressing_old_role_button_is_already_member(
    db: Database, users: UserService, owner: User
) -> None:
    req = await _request(users)
    await users.approve_access(owner, req.user.id)
    again = await _request(users, Role.DIRECTOR)
    assert again.result == RequestResult.ALREADY_MEMBER
    assert again.user.role == Role.EDITOR  # unchanged


# ---- approve / reject -------------------------------------------------------


async def test_owner_approves_with_requested_role(db: Database, users: UserService, owner: User) -> None:
    req = await _request(users, Role.CONTENT_SPECIALIST)
    approved = await users.approve_access(owner, req.user.id)

    assert approved.access_status == AccessStatus.APPROVED and approved.is_active
    assert approved.role == Role.CONTENT_SPECIALIST
    assert approved.capabilities == ["CREATE_REEL", "REVIEW_L1"]
    active = await users.get_active_by_telegram_id(STRANGER_TG)
    assert active is not None and active.id == req.user.id

    events = [e for e in await _all(db, AuditEvent) if e.action == "access.approved"]
    assert len(events) == 1
    assert events[0].actor_id == owner.id
    assert events[0].data["requested_role"] == "CONTENT_SPECIALIST"
    assert events[0].data["after"]["role"] == "CONTENT_SPECIALIST"

    to_user = [n for n in await _all(db, Notification) if n.chat_id == STRANGER_TG]
    assert len(to_user) == 1 and to_user[0].kind == KIND_ACCESS_APPROVED and to_user[0].urgent

    again = await users.start(telegram_id=STRANGER_TG, full_name="Sina", username="sina")
    assert again.result == StartResult.KNOWN


async def test_owner_approves_with_a_different_role(db: Database, users: UserService, owner: User) -> None:
    req = await _request(users, Role.DIRECTOR)  # asked for too much
    approved = await users.approve_access(owner, req.user.id, Role.EDITOR.value)
    assert approved.role == Role.EDITOR and approved.capabilities == []
    event = [e for e in await _all(db, AuditEvent) if e.action == "access.approved"][0]
    assert event.data["requested_role"] == "DIRECTOR"
    assert event.data["after"]["role"] == "EDITOR"


@pytest.mark.parametrize("role", list(ROLE_DEFAULT_CAPABILITIES))
async def test_approval_stores_role_defaults(
    db: Database, users: UserService, owner: User, role: Role
) -> None:
    req = await _request(users)
    if role == Role.OWNER:
        with pytest.raises(InvalidRole):
            await users.approve_access(owner, req.user.id, role)
        return
    approved = await users.approve_access(owner, req.user.id, role)
    assert approved.capabilities == default_capabilities(role)


async def test_owner_rejects(db: Database, users: UserService, owner: User) -> None:
    req = await _request(users)
    rejected = await users.reject_access(owner, req.user.id)
    assert rejected.access_status == AccessStatus.REJECTED and rejected.is_active is False
    assert await users.get_active_by_telegram_id(STRANGER_TG) is None
    assert "access.rejected" in await _audit_actions(db)
    to_user = [n for n in await _all(db, Notification) if n.chat_id == STRANGER_TG]
    assert [n.kind for n in to_user] == [KIND_ACCESS_REJECTED]


async def test_second_decision_is_refused(db: Database, users: UserService, owner: User) -> None:
    req = await _request(users)
    await users.approve_access(owner, req.user.id)
    with pytest.raises(AlreadyDecided) as info:
        await users.reject_access(owner, req.user.id)
    assert info.value.current_status == "APPROVED"
    with pytest.raises(AlreadyDecided):
        await users.approve_access(owner, req.user.id, Role.DIRECTOR)
    with pytest.raises(AlreadyDecided):
        await users.pending_request(owner, req.user.id)
    assert (await _audit_actions(db)).count("access.approved") == 1


@pytest.mark.parametrize("role", [r for r in Role if r != Role.OWNER])
async def test_only_owner_can_decide_access(
    db: Database, users: UserService, owner, role: Role
) -> None:
    """Even the DIRECTOR (who has MANAGE_USERS) cannot approve access — only the OWNER."""
    actor = await add_user(
        db, telegram_id=900, role=role, capabilities=list(ROLE_DEFAULT_CAPABILITIES[role])
    )
    req = await _request(users)
    with pytest.raises(PermissionDenied):
        await users.approve_access(actor, req.user.id)
    with pytest.raises(PermissionDenied):
        await users.reject_access(actor, req.user.id)
    with pytest.raises(PermissionDenied):
        await users.pending_request(actor, req.user.id)
    still = await users.get(req.user.id)
    assert still is not None and still.access_status == AccessStatus.PENDING


async def test_capability_list_alone_does_not_grant_access_decisions(
    db: Database, users: UserService, owner
) -> None:
    actor = await add_user(db, telegram_id=901, role=Role.EDITOR, capabilities=list(Capability))
    req = await _request(users)
    with pytest.raises(PermissionDenied):
        await users.approve_access(actor, req.user.id)


async def test_permission_is_rechecked_from_db(db: Database, users: UserService, owner: User) -> None:
    """A stale in-memory OWNER object must not be trusted once the DB says otherwise."""
    req = await _request(users)
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
    req = await _request(users)
    await users.reject_access(owner, req.user.id)
    clock.advance(hours=1)
    assert (await users.start(telegram_id=STRANGER_TG, full_name="S", username=None)).result == (
        StartResult.ALREADY_REQUESTED
    )
    clock.advance(hours=24)
    again = await _request(users, Role.PROJECT_MANAGER)
    assert again.result == RequestResult.REQUEST_SENT
    assert again.user.access_status == AccessStatus.PENDING
    approved = await users.approve_access(owner, req.user.id)
    assert approved.role == Role.PROJECT_MANAGER
    assert await users.get_active_by_telegram_id(STRANGER_TG) is not None
