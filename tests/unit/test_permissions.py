"""Capabilities and main-menu visibility (handoff §3.1, §3.2, §5.2)."""

from __future__ import annotations

import pytest

from eventum_hq.core.errors import PermissionDenied
from eventum_hq.models import AccessStatus, Capability, Role
from eventum_hq.services.permissions import (
    ALL_CAPABILITIES,
    MenuItem,
    can_use_menu_item,
    effective_capabilities,
    has_capability,
    require_capability,
    visible_menu_items,
)
from tests.conftest import make_user

C = Capability
M = MenuItem

# The six team members exactly as in handoff §3.1
TEAM = {
    "farid": make_user(role=Role.OWNER),
    "ali": make_user(
        role=Role.MANAGER,
        capabilities=[
            C.CREATE_TASK,
            C.VIEW_ALL_TASKS,
            C.RECEIVE_OVERDUE_ALERTS,
            C.RECEIVE_WEEKLY_REPORT,
        ],
    ),
    "amin": make_user(capabilities=[C.CREATE_REEL, C.REVIEW_L1]),
    "barbod": make_user(capabilities=[C.PUBLISH, C.SYSTEM_ADMIN]),
    "sina": make_user(),
    "mohadeseh": make_user(),
}

EXPECTED_MENU = {
    "farid": [
        M.MY_TASKS, M.LIBRARY, M.NEW_REEL, M.REVIEW_QUEUE, M.APPROVAL_QUEUE,
        M.READY_TO_PUBLISH, M.NEW_TASK, M.ALL_TASKS, M.REPORT, M.TEAM, M.HELP,
    ],
    "ali": [M.MY_TASKS, M.LIBRARY, M.NEW_TASK, M.ALL_TASKS, M.REPORT, M.HELP],
    "amin": [M.MY_TASKS, M.LIBRARY, M.NEW_REEL, M.REVIEW_QUEUE, M.HELP],
    "barbod": [M.MY_TASKS, M.LIBRARY, M.READY_TO_PUBLISH, M.HELP],
    "sina": [M.MY_TASKS, M.LIBRARY, M.HELP],
    "mohadeseh": [M.MY_TASKS, M.LIBRARY, M.HELP],
}


@pytest.mark.parametrize("person", list(TEAM))
def test_menu_matches_handoff_for_each_team_member(person: str) -> None:
    assert visible_menu_items(TEAM[person]) == EXPECTED_MENU[person]


@pytest.mark.parametrize("person", list(TEAM))
@pytest.mark.parametrize("item", list(MenuItem))
def test_can_use_menu_item_agrees_with_visible_items(person: str, item: MenuItem) -> None:
    user = TEAM[person]
    assert can_use_menu_item(user, item) == (item in EXPECTED_MENU[person])


def test_owner_has_every_capability_implicitly() -> None:
    assert effective_capabilities(TEAM["farid"]) == ALL_CAPABILITIES
    for cap in (C.APPROVE_FINAL, C.MANAGE_USERS, C.DELEGATE, C.SYSTEM_ADMIN):
        assert has_capability(TEAM["farid"], cap)


def test_only_owner_can_manage_users() -> None:
    for person, user in TEAM.items():
        assert has_capability(user, C.MANAGE_USERS) == (person == "farid")


@pytest.mark.parametrize(
    ("is_active", "status"),
    [
        (False, AccessStatus.APPROVED),
        (True, AccessStatus.PENDING),
        (True, AccessStatus.REJECTED),
        (False, AccessStatus.PENDING),
    ],
)
def test_inactive_or_unapproved_users_have_nothing(is_active: bool, status: AccessStatus) -> None:
    user = make_user(role=Role.OWNER, is_active=is_active, access_status=status)
    assert effective_capabilities(user) == frozenset()
    assert visible_menu_items(user) == []
    with pytest.raises(PermissionDenied):
        require_capability(user, C.MANAGE_USERS)


def test_unknown_capability_strings_are_ignored() -> None:
    user = make_user()
    user.capabilities = ["PUBLISH", "NOT_A_REAL_CAP"]
    assert effective_capabilities(user) == frozenset({C.PUBLISH})


def test_require_capability_raises_for_missing() -> None:
    with pytest.raises(PermissionDenied):
        require_capability(TEAM["sina"], C.CREATE_TASK)
    require_capability(TEAM["ali"], C.CREATE_TASK)  # no error
