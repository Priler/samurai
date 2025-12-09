import databases
import ormar
import sqlalchemy
from sqlalchemy.ext.asyncio import create_async_engine

from config import config

DATABASE_URL = config.db.url

ormar_config = ormar.OrmarConfig(
    database=databases.Database(DATABASE_URL),
    metadata=sqlalchemy.MetaData(),
    engine=create_async_engine(DATABASE_URL),
)


async def init_db() -> None:
    if not ormar_config.database.is_connected:
        await ormar_config.database.connect()


async def close_db() -> None:
    if ormar_config.database.is_connected:
        await ormar_config.database.disconnect()
