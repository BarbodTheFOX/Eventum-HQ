"""Roles, capabilities and main-menu visibility (handoff v1.1 §3 and §5.2).

Pure functions — no database, no aiogram. Callers pass a freshly loaded ``User``.
"""

from __future__ import annotations

from enum import StrEnum

from eventum_hq.core.errors import PermissionDenied
from eventum_hq.models import Capability, Role, Task, User

ALL_CAPABILITIES: frozenset[Capability] = frozenset(Capability)

C = Capability

# Roles a new user may pick when asking for access (OWNER is never selectable).
SELECTABLE_ROLES: tuple[Role, ...] = (
    Role.DIRECTOR,
    Role.PROJECT_MANAGER,
    Role.CONTENT_SPECIALIST,
    Role.DESIGNER,
    Role.EDITOR,
)

# Capabilities stored on approval. OWNER implicitly has everything; the list
# below is only what the OWNER's "normal view" menu is built from.
ROLE_DEFAULT_CAPABILITIES: dict[Role, tuple[Capability, ...]] = {
    Role.OWNER: (C.PUBLISH, C.SYSTEM_ADMIN),
    Role.DIRECTOR: (
        C.APPROVE_FINAL,
        C.DELEGATE,
        C.MANAGE_USERS,
        C.CREATE_TASK,
        C.VIEW_ALL_TASKS,
        C.RECEIVE_OVERDUE_ALERTS,
        C.RECEIVE_WEEKLY_REPORT,
    ),
    Role.PROJECT_MANAGER: (
        C.CREATE_TASK,
        C.VIEW_ALL_TASKS,
        C.RECEIVE_OVERDUE_ALERTS,
        C.RECEIVE_WEEKLY_REPORT,
    ),
    Role.CONTENT_SPECIALIST: (C.CREATE_REEL, C.REVIEW_L1),
    Role.DESIGNER: (),
    Role.EDITOR: (),
}


def default_capabilities(role: Role) -> list[str]:
    return [c.value for c in ROLE_DEFAULT_CAPABILITIES[role]]


def stored_capabilities(user: User) -> frozenset[Capability]:
    """Capabilities explicitly saved on the user (ignores the OWNER's implicit ones).

    Use this to decide who *receives* role-specific work, e.g. final-approval
    cards go to holders of a stored ``APPROVE_FINAL`` (Farid), not to the OWNER.
    """
    if not user.can_use_bot:
        return frozenset()
    known = {c.value for c in Capability}
    return frozenset(Capability(c) for c in (user.capabilities or []) if c in known)


def effective_capabilities(user: User) -> frozenset[Capability]:
    """What the user is allowed to do. OWNER has all; inactive users have none."""
    if not user.can_use_bot:
        return frozenset()
    if user.role == Role.OWNER:
        return ALL_CAPABILITIES
    return stored_capabilities(user)


def has_capability(user: User, capability: Capability) -> bool:
    return capability in effective_capabilities(user)


def require_capability(user: User, capability: Capability) -> None:
    if not has_capability(user, capability):
        raise PermissionDenied(capability.value)


def is_owner(user: User) -> bool:
    return user.can_use_bot and user.role == Role.OWNER


# ---- tasks (handoff §3.2) ----------------------------------------------------


def can_view_task(user: User, task: Task) -> bool:
    """Assignee, creator, or anyone with VIEW_ALL_TASKS."""
    if not user.can_use_bot:
        return False
    return (
        task.assignee_id == user.id
        or task.created_by == user.id
        or has_capability(user, C.VIEW_ALL_TASKS)
    )


def can_manage_task(user: User, task: Task) -> bool:
    """Edit deadline / reassign / cancel: CREATE_TASK holders or the task's creator."""
    if not user.can_use_bot:
        return False
    return has_capability(user, C.CREATE_TASK) or task.created_by == user.id


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
    ADMIN_VIEW_ON = "ADMIN_VIEW_ON"  # OWNER only
    ADMIN_VIEW_OFF = "ADMIN_VIEW_OFF"  # OWNER only


# Order = order on the keyboard (handoff §5.2). None = everyone.
_MENU_RULES: tuple[tuple[MenuItem, Capability | None], ...] = (
    (MenuItem.MY_TASKS, None),
    (MenuItem.LIBRARY, None),
    (MenuItem.NEW_REEL, C.CREATE_REEL),
    (MenuItem.REVIEW_QUEUE, C.REVIEW_L1),
    # Delegates (§4.4) are added in M2 together with delegations.
    (MenuItem.APPROVAL_QUEUE, C.APPROVE_FINAL),
    (MenuItem.READY_TO_PUBLISH, C.PUBLISH),
    (MenuItem.NEW_TASK, C.CREATE_TASK),
    (MenuItem.ALL_TASKS, C.VIEW_ALL_TASKS),
    (MenuItem.REPORT, C.RECEIVE_WEEKLY_REPORT),
    (MenuItem.TEAM, C.MANAGE_USERS),
    (MenuItem.HELP, None),
)
_ADMIN_TOGGLES = (MenuItem.ADMIN_VIEW_ON, MenuItem.ADMIN_VIEW_OFF)


def _items_for(capabilities: frozenset[Capability]) -> list[MenuItem]:
    return [item for item, cap in _MENU_RULES if cap is None or cap in capabilities]


def can_use_menu_item(user: User, item: MenuItem) -> bool:
    """Server-side permission check for a menu item (independent of the view)."""
    if not user.can_use_bot:
        return False
    if item in _ADMIN_TOGGLES:
        return is_owner(user)
    return item in _items_for(effective_capabilities(user))


def visible_menu_items(user: User, *, admin_view: bool = False) -> list[MenuItem]:
    """Buttons shown on the keyboard.

    OWNER: normal view = own work (stored capabilities) + "admin view" button;
    admin view = everything + "normal view" button. ``admin_view`` is ignored
    for everyone else.
    """
    if not user.can_use_bot:
        return []
    if is_owner(user):
        if admin_view:
            return [*_items_for(ALL_CAPABILITIES), MenuItem.ADMIN_VIEW_OFF]
        return [*_items_for(stored_capabilities(user)), MenuItem.ADMIN_VIEW_ON]
    return _items_for(effective_capabilities(user))
