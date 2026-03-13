from datetime import datetime

import ormar

from db.database import ormar_config


class ManagedChat(ormar.Model):
    ormar_config = ormar_config.copy(tablename="managed_chats")

    id: int = ormar.Integer(primary_key=True, autoincrement=True)
    chat_id: int = ormar.BigInteger(unique=True, index=True)
    chat_type: str = ormar.String(max_length=32, default="group")
    title: str = ormar.String(max_length=255, nullable=True)
    bot_status: str = ormar.String(max_length=32, default="administrator")
    is_enabled: bool = ormar.Boolean(default=True)
    updated_at: datetime = ormar.DateTime(default=datetime.now)
