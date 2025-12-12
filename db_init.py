"""
Database initialization script.

This script can be used to init or re-init database tables.
CAUTION: it will DROP ALL DATA in the tables!

Uncomment the exit() line below to run it.
"""
exit("COMMENT THIS LINE IN ORDER TO RE-INIT DATABASE TABLES")

import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from db.database import ormar_config
from db.models import Member, Spam


async def reinit_db_tables() -> None:
    """Drop and recreate all database tables."""
    logger.info("Connecting to database...")
    
    if not ormar_config.database.is_connected:
        await ormar_config.database.connect()

    logger.warning("Dropping all tables...")
    async with ormar_config.engine.begin() as conn:
        await conn.run_sync(ormar_config.metadata.drop_all)
    
    logger.info("Creating tables...")
    async with ormar_config.engine.begin() as conn:
        await conn.run_sync(ormar_config.metadata.create_all)

    await ormar_config.database.disconnect()
    await ormar_config.engine.dispose()
    
    logger.info("Database tables recreated successfully!")


if __name__ == "__main__":
    asyncio.run(reinit_db_tables())
    exit("DONE")


# For SQLite you can also use synchronous version:
# ormar_config.metadata.drop_all(ormar_config.engine)
# ormar_config.metadata.create_all(ormar_config.engine)
