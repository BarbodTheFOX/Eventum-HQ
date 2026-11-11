from aiogram import Router

from eventum_hq.bot.routers import (
    access,
    dates,
    deliver,
    errors,
    groups,
    menu,
    recurrences,
    reels,
    reports,
    review,
    start,
    task_create,
    tasks,
    team,
)


def build_root_router() -> Router:
    root = Router(name="root")
    # Order matters:
    # - task_create (FSM steps) only takes free text, so commands and menu buttons
    #   fall through to the routers below and interrupt a flow (same for the
    #   deliver / review-notes flows);
    # - tasks handles its own menu buttons before the generic menu router;
    # - the menu router ends with a catch-all fallback.
    root.include_routers(
        errors.router,
        groups.router,
        start.router,
        access.router,
        dates.router,
        task_create.router,
        deliver.router,
        review.router,
        team.router,
        recurrences.router,
        reports.router,
        reels.router,
        tasks.router,
        menu.router,
    )
    return root
