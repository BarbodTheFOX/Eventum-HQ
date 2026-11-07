"""Entry point: ``python -m eventum_hq``.

Startup order: settings → logging → migrations → owner bootstrap → polling.
The 60-second scheduler tick is added in M5.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from aiogram.exceptions import TelegramNetworkError, TelegramUnauthorizedError
from aiohttp_socks import ProxyConnectionError, ProxyError, ProxyTimeoutError

from eventum_hq import __version__
from eventum_hq.bot.app import build_bot, build_dispatcher, set_commands
from eventum_hq.bot.outbox import OutboxSender
from eventum_hq.core.config import Settings, load_settings
from eventum_hq.core.db import Database
from eventum_hq.core.errors import ConfigError
from eventum_hq.core.logging import setup_logging
from eventum_hq.core.migrate import upgrade_to_head
from eventum_hq.core.timeutil import SystemClock
from eventum_hq.integrations.sync import NoopSync
from eventum_hq.integrations.telegram_archive import TelegramArchive
from eventum_hq.services.delegations import DelegationService
from eventum_hq.services.reviews import ReviewService
from eventum_hq.services.notifications import OutboxStore
from eventum_hq.services.tasks import TaskService
from eventum_hq.services.users import UserService

log = logging.getLogger("eventum_hq")


async def run(settings: Settings) -> None:
    clock = SystemClock()
    db = Database(settings.database_url)
    users = UserService(db, clock, settings.owner_telegram_id)
    owner = await users.ensure_owner()
    log.info("owner ready user_id=%s", owner.id)

    sync = NoopSync()
    tasks = TaskService(db, clock, sync)
    reviews = ReviewService(db, clock, sync)
    delegations = DelegationService(db, clock)

    bot = build_bot(settings)
    archive = TelegramArchive(bot, settings.archive_channel_id)
    if not archive.configured:
        log.warning("ARCHIVE_CHANNEL_ID is empty: file deliveries are disabled until it is set")
    outbox = OutboxSender(bot, OutboxStore(db, clock), users, tasks, clock, reviews, archive)
    dp = build_dispatcher(
        settings=settings, users=users, tasks=tasks, reviews=reviews, delegations=delegations,
        archive=archive, outbox=outbox, clock=clock,
    )
    try:
        me = await bot.get_me()
        log.info("connected as @%s (id=%s)", me.username, me.id)
        await set_commands(bot)
        await outbox.flush_urgent()  # anything left from before a restart
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        await db.dispose()


def main() -> None:
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        sys.exit(2)

    setup_logging(
        settings.log_level, settings.log_dir, secrets=[settings.bot_token.get_secret_value()]
    )
    log.info(
        "Eventum HQ v%s starting (proxy=%s)", __version__, "on" if settings.telegram_proxy else "off"
    )
    upgrade_to_head(settings.database_url)
    log.info("database migrations are up to date")
    try:
        asyncio.run(run(settings))
    except KeyboardInterrupt:
        pass
    except TelegramUnauthorizedError:
        log.error("Telegram rejected BOT_TOKEN. Check the token in .env (use the TEST bot).")
        sys.exit(3)
    except (TelegramNetworkError, ProxyError, ProxyConnectionError, ProxyTimeoutError) as exc:
        log.error(
            "Cannot reach api.telegram.org (%s). Is the VPN on? Check TELEGRAM_PROXY in .env "
            "(e.g. socks5://127.0.0.1:10808), or leave it empty in TUN mode.",
            exc,
        )
        sys.exit(4)
    finally:
        log.info("Eventum HQ stopped")


if __name__ == "__main__":
    main()
