"""Task state machine (handoff §4.3).

    BLOCKED ─(input arrived)─▶ TODO ─(start)─▶ IN_PROGRESS ─(submit)─▶ IN_REVIEW
    TODO ─(direct submit)─▶ IN_REVIEW
    IN_REVIEW ─(changes)─▶ CHANGES_REQUESTED ─(start / resubmit)─▶ IN_PROGRESS / IN_REVIEW
    IN_REVIEW ─(last stage approves)─▶ APPROVED
    TODO / IN_PROGRESS ─(“done”, chain NONE only)─▶ APPROVED
    any open state ─(cancel)─▶ CANCELLED

Moving between review stages (L1 → FINAL) keeps status IN_REVIEW and is not a
state transition.
"""

from __future__ import annotations

from eventum_hq.core.errors import InvalidTransition
from eventum_hq.models import TaskStatus

S = TaskStatus

TERMINAL: frozenset[TaskStatus] = frozenset({S.APPROVED, S.CANCELLED})
OPEN: frozenset[TaskStatus] = frozenset(set(TaskStatus) - TERMINAL)

ALLOWED: dict[TaskStatus, frozenset[TaskStatus]] = {
    S.BLOCKED: frozenset({S.TODO, S.CANCELLED}),
    S.TODO: frozenset({S.IN_PROGRESS, S.IN_REVIEW, S.APPROVED, S.CANCELLED}),
    S.IN_PROGRESS: frozenset({S.IN_REVIEW, S.APPROVED, S.CANCELLED}),
    S.IN_REVIEW: frozenset({S.CHANGES_REQUESTED, S.APPROVED, S.CANCELLED}),
    S.CHANGES_REQUESTED: frozenset({S.IN_PROGRESS, S.IN_REVIEW, S.CANCELLED}),
    S.APPROVED: frozenset(),
    S.CANCELLED: frozenset(),
}


def can_transition(current: TaskStatus, target: TaskStatus) -> bool:
    return target in ALLOWED[current]


def ensure_transition(current: TaskStatus, target: TaskStatus) -> None:
    if not can_transition(current, target):
        raise InvalidTransition(str(current), str(target))


def is_open(status: TaskStatus) -> bool:
    return status in OPEN
