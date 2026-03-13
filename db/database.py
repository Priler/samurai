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
    await ensure_runtime_tables()


async def close_db() -> None:
    if ormar_config.database.is_connected:
        await ormar_config.database.disconnect()


async def ensure_runtime_tables() -> None:
    """Create runtime tables if they do not exist."""
    statements = [
        """
        CREATE TABLE IF NOT EXISTS bot_owners (
            id INTEGER PRIMARY KEY,
            user_id BIGINT UNIQUE,
            is_active BOOLEAN NOT NULL DEFAULT 1,
            added_by BIGINT NULL,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_bot_owners_user_id ON bot_owners(user_id)",
        """
        CREATE TABLE IF NOT EXISTS managed_chats (
            id INTEGER PRIMARY KEY,
            chat_id BIGINT UNIQUE,
            chat_type VARCHAR(32) NOT NULL,
            title VARCHAR(255) NULL,
            bot_status VARCHAR(32) NOT NULL,
            is_enabled BOOLEAN NOT NULL DEFAULT 1,
            updated_at TIMESTAMP NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_managed_chats_chat_id ON managed_chats(chat_id)",
        """
        CREATE TABLE IF NOT EXISTS linked_channels (
            id INTEGER PRIMARY KEY,
            group_chat_id BIGINT NOT NULL,
            channel_chat_id BIGINT NOT NULL,
            source VARCHAR(32) NOT NULL,
            updated_at TIMESTAMP NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_linked_channels_group ON linked_channels(group_chat_id)",
        "CREATE INDEX IF NOT EXISTS idx_linked_channels_channel ON linked_channels(channel_chat_id)",
        """
        CREATE TABLE IF NOT EXISTS bot_settings (
            id INTEGER PRIMARY KEY,
            key VARCHAR(128) UNIQUE,
            value TEXT NOT NULL,
            value_type VARCHAR(24) NOT NULL,
            updated_by BIGINT NULL,
            updated_at TIMESTAMP NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_bot_settings_key ON bot_settings(key)",
        """
        CREATE TABLE IF NOT EXISTS chat_settings (
            id INTEGER PRIMARY KEY,
            chat_id BIGINT NOT NULL,
            key VARCHAR(128) NOT NULL,
            value TEXT NOT NULL,
            value_type VARCHAR(24) NOT NULL,
            updated_by BIGINT NULL,
            updated_at TIMESTAMP NOT NULL,
            UNIQUE(chat_id, key)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_chat_settings_chat_key ON chat_settings(chat_id, key)",
        """
        CREATE TABLE IF NOT EXISTS settings_audit_log (
            id INTEGER PRIMARY KEY,
            actor_id BIGINT NULL,
            scope_type VARCHAR(16) NOT NULL,
            scope_id BIGINT NULL,
            key VARCHAR(128) NOT NULL,
            old_value TEXT NULL,
            new_value TEXT NULL,
            created_at TIMESTAMP NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_settings_audit_key ON settings_audit_log(key)",
    ]
    for stmt in statements:
        await ormar_config.database.execute(stmt)
