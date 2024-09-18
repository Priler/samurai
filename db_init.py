exit("COMMENT THIS LINE IN ORDER TO RE-INIT DATABASE TABLES")

import asyncio
import logging
from configurator import make_config

logging.basicConfig(level=logging.INFO)

if not make_config("config.ini"):
    logging.error("Errors while parsing config file. Exiting.")
    exit(1)

import heroku_config

# import models n stuff
from db import ormar_config
from models.member import Member

# DROP & INIT tables (async mysql)
async def reinit_db_tables():
    async with ormar_config.engine.begin() as conn:
        await conn.run_sync(ormar_config.metadata.drop_all)
        await conn.run_sync(ormar_config.metadata.create_all)

    await ormar_config.engine.dispose()

asyncio.run(reinit_db_tables())
exit("DONE")

# for sqlite use this :3
# ormar_config.metadata.drop_all(ormar_config.engine)
# ormar_config.metadata.create_all(ormar_config.engine)