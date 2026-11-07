from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest

from eventum_hq.core.db import Database
from eventum_hq.models import AccessStatus, Base, Capability, Role, User
from eventum_hq.services.users import UserService

OWNER_TG = 1000


class FakeClock:
    """Injectable clock for tests (always aware UTC)."""

    def __init__(self, now: datetime | None = None) -> None:
        self._now = now or datetime(2026, 11, 7, 8, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, **kwargs: float) -> None:
        self._now += timedelta(**kwargs)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
async def db() -> AsyncIterator[Database]:
    database = Database("sqlite+aiosqlite:///:memory:")
    async with database.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield database
    await database.dispose()


@pytest.fixture
def users(db: Database, clock: FakeClock) -> UserService:
    return UserService(db, clock, OWNER_TG)


@pytest.fixture
async def owner(users: UserService) -> User:
    return await users.ensure_owner()


async def add_user(
    db: Database,
    *,
    telegram_id: int,
    role: Role = Role.EDITOR,
    capabilities: list[Capability] | None = None,
    is_active: bool = True,
    access_status: AccessStatus = AccessStatus.APPROVED,
    full_name: str = "Test",
) -> User:
    async with db.transaction() as session:
        user = User(
            telegram_id=telegram_id,
            full_name=full_name,
            role=role,
            capabilities=[c.value for c in capabilities or []],
            is_active=is_active,
            access_status=access_status,
        )
        session.add(user)
    return user


def make_user(
    *,
    role: Role = Role.EDITOR,
    capabilities: list[Capability] | None = None,
    is_active: bool = True,
    access_status: AccessStatus = AccessStatus.APPROVED,
) -> User:
    """Unsaved user object for pure permission tests."""
    return User(
        telegram_id=1,
        full_name="x",
        role=role,
        capabilities=[c.value for c in capabilities or []],
        is_active=is_active,
        access_status=access_status,
    )
