"""
Database initialization script.

This script can be used to init or re-init database tables.
CAUTION: it will DROP ALL DATA in the tables!

Uncomment the exit() line below to run it.
"""
exit("COMMENT THIS LINE IN ORDER TO RE-INIT DATABASE TABLES")

import logging
from sqlalchemy import create_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from db.database import ormar_config
from db.models import (
    Member, Spam, BotOwner, ManagedChat, LinkedChannel,
    BotSetting, ChatSetting, SettingsAuditLog
)


def _to_sync_url(url: str) -> str:
    return (
        url.replace("+aiosqlite", "")
        .replace("+asyncpg", "")
        .replace("+aiomysql", "")
    )


def reinit_db_tables() -> None:
    """Drop and recreate all database tables."""
    logger.info("Creating sync engine for table reset...")
    sync_url = _to_sync_url(str(ormar_config.database.url))
    engine = create_engine(sync_url)

    logger.warning("Dropping all tables...")
    ormar_config.metadata.drop_all(engine)
    
    logger.info("Creating tables...")
    ormar_config.metadata.create_all(engine)
    engine.dispose()
    
    logger.info("Database tables recreated successfully!")


if __name__ == "__main__":
    reinit_db_tables()
    exit("DONE")


# For SQLite you can also use synchronous version:
# ormar_config.metadata.drop_all(ormar_config.engine)
# ormar_config.metadata.create_all(ormar_config.engine)
