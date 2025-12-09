from datetime import datetime

import ormar

from db.database import ormar_config


class Spam(ormar.Model):
    ormar_config = ormar_config.copy(tablename="spam")

    id: int = ormar.Integer(primary_key=True, autoincrement=True)
    message: str = ormar.Text(unique=True)
    is_spam: bool = ormar.Boolean()
    is_blocked: bool = ormar.Boolean(default=False)
    date: datetime = ormar.DateTime(default=datetime.now)
    chat_id: int = ormar.BigInteger(nullable=True)
    user_id: int = ormar.BigInteger(nullable=True)
