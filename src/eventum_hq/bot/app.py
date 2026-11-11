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
from eventum_hq.bot.middlewares import (
    AccessMiddleware,
    FlowTimeoutMiddleware,
    OutboxFlushMiddleware,
)
from eventum_hq.bot.outbox import OutboxSender
from eventum_hq.bot.request_middlewares import IgnoreExpiredCallbackAnswer
from eventum_hq.bot.routers import build_root_router
from eventum_hq.core.config import Settings
from eventum_hq.core.timeutil import Clock
from eventum_hq.integrations.telegram_archive import TelegramArchive
from eventum_hq.services.delegations import DelegationService
from eventum_hq.services.recurrences import RecurrenceService
from eventum_hq.services.reels import ReelService
from eventum_hq.services.reports import ReportService
from eventum_hq.services.reviews import ReviewService
from eventum_hq.services.tasks import TaskService
from eventum_hq.services.users import UserService


def build_bot(settings: Settings) -> Bot:
    session = AiohttpSession(proxy=settings.telegram_proxy) if settings.telegram_proxy else None
    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    bot.session.middleware(IgnoreExpiredCallbackAnswer())
    return bot


def build_dispatcher(
    *,
    settings: Settings,
    users: UserService,
    tasks: TaskService,
    reviews: ReviewService,
    delegations: DelegationService,
    reels: ReelService,
    archive: TelegramArchive,
    outbox: OutboxSender,
    clock: Clock,
    recurrences: RecurrenceService,
    reports: ReportService,
) -> Dispatcher:
    admin_views = AdminViews()
    dp = Dispatcher(
        storage=MemoryStorage(),
        # injected into handlers by parameter name
        users=users,
        tasks=tasks,
        reviews=reviews,
        delegations=delegations,
        reels=reels,
        recurrences=recurrences,
        reports=reports,
        archive=archive,
        outbox=outbox,
        clock=clock,
        admin_views=admin_views,
        team_group_id=settings.team_group_id,
        owner_telegram_id=settings.owner_telegram_id,
    )
    # Outer middlewares run in registration order: flush wraps the access gate.
    dp.update.outer_middleware(OutboxFlushMiddleware(outbox))
    dp.update.outer_middleware(AccessMiddleware(users, delegations, admin_views))
    timeout = FlowTimeoutMiddleware(clock)
    dp.message.outer_middleware(timeout)
    dp.callback_query.outer_middleware(timeout)
    dp.include_router(build_root_router())
    return dp


async def set_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [BotCommand(command=c, description=d) for c, d in texts.COMMANDS.items()],
        scope=BotCommandScopeAllPrivateChats(),
    )
