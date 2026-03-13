from datetime import datetime

import ormar

from db.database import ormar_config


class BotOwner(ormar.Model):
    ormar_config = ormar_config.copy(tablename="bot_owners")

    id: int = ormar.Integer(primary_key=True, autoincrement=True)
    user_id: int = ormar.BigInteger(unique=True, index=True)
    is_active: bool = ormar.Boolean(default=True)
    added_by: int = ormar.BigInteger(nullable=True)
    created_at: datetime = ormar.DateTime(default=datetime.now)
    updated_at: datetime = ormar.DateTime(default=datetime.now)
