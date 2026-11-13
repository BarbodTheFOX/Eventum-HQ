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


class NewReelFlow(StatesGroup):
    title = State()
    subtype = State()
    edit_type = State()
    series = State()
    timecodes = State()
    cover_text = State()
    edit_assignee = State()
    cover_assignee = State()
    confirm = State()
    estimate = State()  # changing one estimate from the confirm screen


class PhotosFlow(StatesGroup):
    """Cover photos from the edit assignee. Data: edit_task_id, reel_code, title, items."""

    collect = State()


class PublishFlow(StatesGroup):
    """Publish links for a ready reel. Data: item_id, code, links."""

    links = State()


PURPOSE_REEL_PUBLISH = "reel_publish"
PURPOSE_REEL_DEADLINE = "reel_deadline"
PURPOSE_PUBLISHED_AT = "published_at"


class LibraryFlow(StatesGroup):
    """📚 library is open: any free text is a search. Data: lib_query (last search text)."""

    search = State()


class RecurrenceFlow(StatesGroup):
    """➕ new recurring task (F10). Data: title, assignee_id, rule, weekdays, create_time, due_time, chain."""

    title = State()
    assignee = State()
    rule = State()
    weekdays = State()
    create_time = State()
    due_time = State()
    chain = State()
    estimate = State()
    confirm = State()


class DailyReportFlow(StatesGroup):
    """📝 daily report is open: every free text is an evening note (stored in the DB, not in FSM)."""

    notes = State()
