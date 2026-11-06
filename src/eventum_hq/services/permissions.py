"""Roles, capabilities and main-menu visibility (handoff §3 and §5.2).

Pure functions — no database, no aiogram. Callers pass a freshly loaded ``User``.
"""

from __future__ import annotations

from enum import StrEnum

from eventum_hq.core.errors import PermissionDenied
from eventum_hq.models import Capability, Role, User

ALL_CAPABILITIES: frozenset[Capability] = frozenset(Capability)


def effective_capabilities(user: User) -> frozenset[Capability]:
    """Capabilities the user really has. OWNER has all; inactive users have none."""
    if not user.can_use_bot:
        return frozenset()
    if user.role == Role.OWNER:
        return ALL_CAPABILITIES
    known = {c.value for c in Capability}
    return frozenset(Capability(c) for c in (user.capabilities or []) if c in known)


def has_capability(user: User, capability: Capability) -> bool:
    return capability in effective_capabilities(user)


def require_capability(user: User, capability: Capability) -> None:
    if not has_capability(user, capability):
        raise PermissionDenied(capability.value)


def is_owner(user: User) -> bool:
    return user.can_use_bot and user.role == Role.OWNER


class MenuItem(StrEnum):
    MY_TASKS = "MY_TASKS"
    LIBRARY = "LIBRARY"
    NEW_REEL = "NEW_REEL"
    REVIEW_QUEUE = "REVIEW_QUEUE"
    APPROVAL_QUEUE = "APPROVAL_QUEUE"
    READY_TO_PUBLISH = "READY_TO_PUBLISH"
    NEW_TASK = "NEW_TASK"
    ALL_TASKS = "ALL_TASKS"
    REPORT = "REPORT"
    TEAM = "TEAM"
    HELP = "HELP"


# Order = order on the keyboard (handoff §5.2).
_MENU_RULES: tuple[tuple[MenuItem, Capability | None], ...] = (
    (MenuItem.MY_TASKS, None),
    (MenuItem.LIBRARY, None),
    (MenuItem.NEW_REEL, Capability.CREATE_REEL),
    (MenuItem.REVIEW_QUEUE, Capability.REVIEW_L1),
    # OWNER only; the temporary delegate (§4.4) is added in M2 with delegations.
    (MenuItem.APPROVAL_QUEUE, Capability.APPROVE_FINAL),
    (MenuItem.READY_TO_PUBLISH, Capability.PUBLISH),
    (MenuItem.NEW_TASK, Capability.CREATE_TASK),
    (MenuItem.ALL_TASKS, Capability.VIEW_ALL_TASKS),
    (MenuItem.REPORT, None),  # role-based, see below
    (MenuItem.TEAM, Capability.MANAGE_USERS),
    (MenuItem.HELP, None),
)


def can_use_menu_item(user: User, item: MenuItem) -> bool:
    if not user.can_use_bot:
        return False
    if item == MenuItem.REPORT:
        return user.role in (Role.OWNER, Role.MANAGER)
    for rule_item, capability in _MENU_RULES:
        if rule_item == item:
            return capability is None or has_capability(user, capability)
    return False


def visible_menu_items(user: User) -> list[MenuItem]:
    return [item for item, _ in _MENU_RULES if can_use_menu_item(user, item)]
