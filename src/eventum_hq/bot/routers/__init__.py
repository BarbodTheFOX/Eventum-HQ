from aiogram import Router

from eventum_hq.bot.routers import access, errors, groups, menu, start


def build_root_router() -> Router:
    root = Router(name="root")
    # order matters: the menu router ends with a catch-all fallback
    root.include_routers(errors.router, groups.router, start.router, access.router, menu.router)
    return root
