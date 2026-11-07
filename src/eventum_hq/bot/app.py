"""Wires aiogram Bot + Dispatcher with services and middlewares."""

from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats

from eventum_hq.bot import texts
from eventum_hq.bot.keyboards.main_menu import AdminViews
from eventum_hq.bot.middlewares import AccessMiddleware, OutboxFlushMiddleware
from eventum_hq.bot.outbox import OutboxSender
from eventum_hq.bot.routers import build_root_router
from eventum_hq.core.config import Settings
from eventum_hq.services.users import UserService


def build_bot(settings: Settings) -> Bot:
    session = AiohttpSession(proxy=settings.telegram_proxy) if settings.telegram_proxy else None
    return Bot(
        token=settings.bot_token.get_secret_value(),
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def build_dispatcher(
    *, settings: Settings, users: UserService, outbox: OutboxSender
) -> Dispatcher:
    dp = Dispatcher(
        storage=MemoryStorage(),
        # injected into handlers by parameter name
        users=users,
        outbox=outbox,
        admin_views=AdminViews(),
        team_group_id=settings.team_group_id,
    )
    # Outer middlewares run in registration order: flush wraps the access gate.
    dp.update.outer_middleware(OutboxFlushMiddleware(outbox))
    dp.update.outer_middleware(AccessMiddleware(users))
    dp.include_router(build_root_router())
    return dp


async def set_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [BotCommand(command=c, description=d) for c, d in texts.COMMANDS.items()],
        scope=BotCommandScopeAllPrivateChats(),
    )
