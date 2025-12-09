"""
Database initialization script.
Run this once to create the database tables.
"""
import asyncio

from db.database import ormar_config
from db.models import Member, Spam


async def init_database() -> None:
    """Initialize the database and create tables."""
    # Connect to database
    if not ormar_config.database.is_connected:
        await ormar_config.database.connect()

    # Create tables using SQLAlchemy
    async with ormar_config.engine.begin() as conn:
        await conn.run_sync(ormar_config.metadata.create_all)

    print("Database tables created successfully!")

    # Disconnect
    await ormar_config.database.disconnect()


if __name__ == "__main__":
    asyncio.run(init_database())
