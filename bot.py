from aiogram import executor
from dispatcher import dp
import handlers
import announcements
import asyncio

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(announcements.scheduler())
    executor.start_polling(dp, skip_updates=True)
