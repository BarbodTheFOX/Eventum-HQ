"""FSM states. MemoryStorage: an unfinished flow is lost on restart (accepted in v0)."""

from aiogram.fsm.state import State, StatesGroup


class NewTaskFlow(StatesGroup):
    title = State()
    description = State()
    assignee = State()
    estimate = State()
    series = State()
    chain = State()
    confirm = State()


class DateInput(StatesGroup):
    """Shared deadline picker. FSM data ``date_purpose``: 'new' (create flow) or 'due' (edit)."""

    date = State()
    time = State()
    past_confirm = State()


# keys in FSM data
PURPOSE_NEW = "new"
PURPOSE_DUE = "due"


class SubmitFlow(StatesGroup):
    """Collect files / links / note for one delivery. Data: task_id, items, links, note."""

    collect = State()


class ReviewNotesFlow(StatesGroup):
    """Collect change-request notes. Data: submission_id, version, stage, texts, files."""

    collect = State()


PURPOSE_DELEGATION = "delegation"
