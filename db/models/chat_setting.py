from datetime import datetime

import ormar

from db.database import ormar_config


class ChatSetting(ormar.Model):
    ormar_config = ormar_config.copy(tablename="chat_settings")

    id: int = ormar.Integer(primary_key=True, autoincrement=True)
    chat_id: int = ormar.BigInteger(index=True)
    key: str = ormar.String(max_length=128, index=True)
    value: str = ormar.Text(default="")
    value_type: str = ormar.String(max_length=24, default="str")
    updated_by: int = ormar.BigInteger(nullable=True)
    updated_at: datetime = ormar.DateTime(default=datetime.now)
