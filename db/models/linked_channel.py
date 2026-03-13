from datetime import datetime

import ormar

from db.database import ormar_config


class LinkedChannel(ormar.Model):
    ormar_config = ormar_config.copy(tablename="linked_channels")

    id: int = ormar.Integer(primary_key=True, autoincrement=True)
    group_chat_id: int = ormar.BigInteger(index=True)
    channel_chat_id: int = ormar.BigInteger(index=True)
    source: str = ormar.String(max_length=32, default="manual")
    updated_at: datetime = ormar.DateTime(default=datetime.now)
