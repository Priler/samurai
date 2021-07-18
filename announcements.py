import dispatcher
import configurator
import localization
import asyncio
import aioschedule as schedule

async def announce(message):
	await dispatcher.dp.bot.send_message(configurator.config.groups.main, message)

async def scheduler():
    for i in localization.get_string('announcements'):
         schedule.every(i['every']).seconds.do(announce, i['message'])

    while True:
        await schedule.run_pending()
        await asyncio.sleep(2)