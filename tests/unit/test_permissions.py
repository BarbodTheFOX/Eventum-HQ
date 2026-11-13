"""Roles, capabilities and main-menu visibility (handoff v1.1 §3.1, §3.2, §5.2)."""

from __future__ import annotations

import pytest

from eventum_hq.core.errors import PermissionDenied
from eventum_hq.models import AccessStatus, Capability, Role
from eventum_hq.services.permissions import (
    ALL_CAPABILITIES,
    ROLE_DEFAULT_CAPABILITIES,
    SELECTABLE_ROLES,
    MenuItem,
    can_use_menu_item,
    default_capabilities,
    effective_capabilities,
    has_capability,
    require_capability,
    stored_capabilities,
    visible_menu_items,
)
from tests.conftest import make_user

C = Capability
M = MenuItem


def member(role: Role):  # type: ignore[no-untyped-def]
    """A user approved with the role's default capabilities (as approve_access does)."""
    return make_user(role=role, capabilities=list(ROLE_DEFAULT_CAPABILITIES[role]))


# The six team members (handoff v1.1 §3.1)
TEAM = {
    "barbod": member(Role.OWNER),
    "farid": member(Role.DIRECTOR),
    "ali": member(Role.PROJECT_MANAGER),
    "amin": member(Role.CONTENT_SPECIALIST),
    "mohadeseh": member(Role.DESIGNER),
    "sina": member(Role.EDITOR),
}

FULL_MENU = [
    M.MY_TASKS, M.LIBRARY, M.NEW_REEL, M.REVIEW_QUEUE, M.APPROVAL_QUEUE,
    M.READY_TO_PUBLISH, M.NEW_TASK, M.ALL_TASKS, M.REPORT, M.DAILY_REPORT, M.TEAM, M.HELP,
]

EXPECTED_MENU = {
    # Barbod's normal view: his own work + the daily report (M7) + the admin-view button
    "barbod": [M.MY_TASKS, M.LIBRARY, M.READY_TO_PUBLISH, M.DAILY_REPORT, M.HELP, M.ADMIN_VIEW_ON],
    "farid": [
        M.MY_TASKS, M.LIBRARY, M.APPROVAL_QUEUE, M.NEW_TASK, M.ALL_TASKS, M.REPORT, M.DAILY_REPORT, M.TEAM,
        M.HELP,
    ],
    "ali": [M.MY_TASKS, M.LIBRARY, M.NEW_TASK, M.ALL_TASKS, M.REPORT, M.DAILY_REPORT, M.HELP],
    "amin": [M.MY_TASKS, M.LIBRARY, M.NEW_REEL, M.REVIEW_QUEUE, M.HELP],
    "mohadeseh": [M.MY_TASKS, M.LIBRARY, M.HELP],
    "sina": [M.MY_TASKS, M.LIBRARY, M.HELP],
}


@pytest.mark.parametrize("person", list(TEAM))
def test_menu_matches_handoff_for_each_team_member(person: str) -> None:
    assert visible_menu_items(TEAM[person]) == EXPECTED_MENU[person]


def test_owner_admin_view_shows_everything() -> None:
    assert visible_menu_items(TEAM["barbod"], admin_view=True) == [*FULL_MENU, M.ADMIN_VIEW_OFF]


@pytest.mark.parametrize("person", [p for p in TEAM if p != "barbod"])
def test_admin_view_flag_is_ignored_for_non_owners(person: str) -> None:
    assert visible_menu_items(TEAM[person], admin_view=True) == EXPECTED_MENU[person]


@pytest.mark.parametrize("person", [p for p in TEAM if p != "barbod"])
@pytest.mark.parametrize("item", list(MenuItem))
def test_can_use_menu_item_agrees_with_visible_items(person: str, item: MenuItem) -> None:
    user = TEAM[person]
    assert can_use_menu_item(user, item) == (item in EXPECTED_MENU[person])


@pytest.mark.parametrize("item", list(MenuItem))
def test_owner_may_use_every_item_in_any_view(item: MenuItem) -> None:
    assert can_use_menu_item(TEAM["barbod"], item)


def test_owner_has_every_capability_but_only_stored_ones_for_routing() -> None:
    barbod = TEAM["barbod"]
    assert effective_capabilities(barbod) == ALL_CAPABILITIES
    # final-approval cards go to stored APPROVE_FINAL holders (Farid), not Barbod
    assert C.APPROVE_FINAL not in stored_capabilities(barbod)
    assert C.APPROVE_FINAL in stored_capabilities(TEAM["farid"])


def test_only_director_and_owner_manage_the_team() -> None:
    for person, user in TEAM.items():
        assert has_capability(user, C.MANAGE_USERS) == (person in {"barbod", "farid"})


def test_selectable_roles_exclude_owner() -> None:
    assert Role.OWNER not in SELECTABLE_ROLES
    assert set(SELECTABLE_ROLES) == set(Role) - {Role.OWNER}


def test_default_capabilities_are_strings() -> None:
    assert default_capabilities(Role.CONTENT_SPECIALIST) == ["CREATE_REEL", "REVIEW_L1"]
    assert default_capabilities(Role.EDITOR) == []


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
    assert visible_menu_items(user, admin_view=True) == []
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
