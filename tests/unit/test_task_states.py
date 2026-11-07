"""Every allowed and every forbidden task transition (handoff §4.3, §10)."""

from __future__ import annotations

import pytest

from eventum_hq.core.errors import InvalidTransition
from eventum_hq.models import TaskStatus
from eventum_hq.services.task_states import OPEN, TERMINAL, can_transition, ensure_transition

S = TaskStatus

EXPECTED_ALLOWED = {
    (S.BLOCKED, S.TODO),
    (S.TODO, S.IN_PROGRESS),
    (S.TODO, S.IN_REVIEW),
    (S.TODO, S.APPROVED),  # chain NONE
    (S.IN_PROGRESS, S.IN_REVIEW),
    (S.IN_PROGRESS, S.APPROVED),  # chain NONE
    (S.IN_REVIEW, S.CHANGES_REQUESTED),
    (S.IN_REVIEW, S.APPROVED),
    (S.CHANGES_REQUESTED, S.IN_PROGRESS),
    (S.CHANGES_REQUESTED, S.IN_REVIEW),
} | {(s, S.CANCELLED) for s in OPEN}

ALL_PAIRS = [(a, b) for a in TaskStatus for b in TaskStatus]


@pytest.mark.parametrize(("current", "target"), ALL_PAIRS)
def test_transition_matrix(current: TaskStatus, target: TaskStatus) -> None:
    allowed = (current, target) in EXPECTED_ALLOWED
    assert can_transition(current, target) is allowed
    if allowed:
        ensure_transition(current, target)
    else:
        with pytest.raises(InvalidTransition):
            ensure_transition(current, target)


def test_terminal_states() -> None:
    assert TERMINAL == {S.APPROVED, S.CANCELLED}
    for status in TERMINAL:
        assert not any(can_transition(status, t) for t in TaskStatus)
