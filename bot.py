# Main entry point.

import asyncio
import logging
import sys
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import config
from db import init_db, close_db
from handlers import register_all_handlers
from middlewares import register_all_middlewares
from services.announcements import setup_announcements, run_scheduler
from services.healthcheck import start_health_server, stop_health_server, get_health_server
from services.cache import start_batch_flush_task, stop_batch_flush_task, flush_member_updates

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot) -> None:
    """Startup hook."""
    logger.info("Bot starting up...")

    # Initialize database
    await init_db()
    logger.info("Database connected")

    # Start batch member update flush task (interval from config)
    start_batch_flush_task()
    logger.info("Batch flush task started")

    # Setup announcements
    await setup_announcements(bot)
    logger.info("Announcements scheduled")

    # Set health check to ready
    if config.healthcheck.enabled:
        get_health_server().set_ready(True)

    logger.info(f"Bot version: {config.bot.version} ({config.bot.version_codename})")


async def on_shutdown(bot: Bot) -> None:
    """Shutdown hook."""
    logger.info("Bot shutting down...")

    # Set health check to not ready
    if config.healthcheck.enabled:
        get_health_server().set_ready(False)

    # Stop batch flush task and flush remaining updates
    stop_batch_flush_task()
    flushed = await flush_member_updates()
    logger.info(f"Flushed {flushed} pending member updates")

    # Close database
    await close_db()
    logger.info("Database disconnected")


async def main() -> None:
    """Main function."""
    # Check token
    if not config.bot.token.get_secret_value():
        logger.error("No bot token provided")
        sys.exit(1)

    # Start health check server
    if config.healthcheck.enabled:
        await start_health_server(
            host=config.healthcheck.host,
            port=config.healthcheck.port
        )

    # Initialize bot and dispatcher
    bot = Bot(
        token=config.bot.token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # Register handlers
    register_all_handlers(dp)

    # Register middlewares
    register_all_middlewares(
        dp,
        default_locale=config.locale.default,
        enable_throttling=config.throttling.enabled,
        throttle_rate=config.throttling.rate_limit,
        throttle_max_messages=config.throttling.max_messages,
        throttle_time_window=config.throttling.time_window
    )

    # Setup startup/shutdown hooks
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Start scheduler as background task
    scheduler_task = asyncio.create_task(run_scheduler())

    logger.info("Bot started")

    try:
        # Start polling (aiogram handles SIGINT/SIGTERM internally)
        await dp.start_polling(bot, skip_updates=True)
    finally:
        # Cancel scheduler
        scheduler_task.cancel()
        with suppress(asyncio.CancelledError):
            await scheduler_task

        # Stop health check server
        if config.healthcheck.enabled:
            await stop_health_server()

        # Close bot session
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
