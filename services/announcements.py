"""
Scheduled announcements service.
"""
import asyncio

import aioschedule as schedule

from config import config
from utils.localization import ANNOUNCEMENTS


async def announce(bot, message: str) -> None:
    """Send announcement to all main chats."""
    for group_id in config.groups.main:
        try:
            await bot.send_message(group_id, message)
        except Exception:
            pass


async def setup_announcements(bot) -> None:
    """Setup scheduled announcements."""
    for announcement in ANNOUNCEMENTS:
        schedule.every(announcement['every']).seconds.do(
            announce,
            bot,
            announcement['message']
        )


async def run_scheduler() -> None:
    """Run the announcement scheduler loop."""
    while True:
        await schedule.run_pending()
        await asyncio.sleep(2)
