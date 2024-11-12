from datetime import datetime

import ormar
from db import ormar_config

class Spam(ormar.Model):
    ormar_config = ormar_config.copy(tablename="spam")

    id: int = ormar.Integer(primary_key=True, auto_increment=True)
    message: str = ormar.Text(unique=True)
    is_spam: bool = ormar.Boolean()
    date: datetime = ormar.DateTime(default=datetime.now)
