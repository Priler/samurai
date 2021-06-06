from dispatcher import dp
from configurator import config
import localization
from time import time
import asyncio
import aioschedule as schedule

# send !report announce every 
async def announce_report():
	await dp.bot.send_message(
        config.groups.main,
        localization.get_string("announce_1"))

# send general announce every
async def announce_general():
	await dp.bot.send_message(
        config.groups.main,
        localization.get_string("announce_2"))

# send cov announce every
async def announce_cov():
	await dp.bot.send_message(
        config.groups.main,
        localization.get_string("announce_3"))


# schedule
async def scheduler():
    schedule.every(18000).seconds.do(announce_report)
    schedule.every(10800).seconds.do(announce_general)
    schedule.every(7200).seconds.do(announce_cov)

    # loop = asyncio.get_event_loop()
    while True:
        await schedule.run_pending()
        await asyncio.sleep(2)