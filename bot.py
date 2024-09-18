from aiogram import executor
from dispatcher import dp
import handlers
import announcements
import asyncio

from db import ormar_config


async def on_startup(dp):
    # connect (all dbs except sqlite require connection)
    if ormar_config.database.is_connected:
        return
    await ormar_config.database.connect()


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(announcements.scheduler())
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)

    # disconnect from database
    ormar_config.database.disconnect()
