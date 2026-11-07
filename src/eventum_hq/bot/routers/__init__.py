from aiogram import Router

from eventum_hq.bot.routers import access, errors, groups, menu, start, task_create, tasks


def build_root_router() -> Router:
    root = Router(name="root")
    # Order matters:
    # - task_create (FSM steps) only takes free text, so commands and menu buttons
    #   fall through to the routers below and interrupt a flow;
    # - tasks handles its own menu buttons before the generic menu router;
    # - the menu router ends with a catch-all fallback.
    root.include_routers(
        errors.router,
        groups.router,
        start.router,
        access.router,
        task_create.router,
        tasks.router,
        menu.router,
    )
    return root
