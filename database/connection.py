import asyncpg
from asyncpg import Pool
import configurator

conn_poll: Pool = await asyncpg.create_pool(dsn=configurator.config.database.url)
conn = await conn_poll.acquire()
