from datetime import datetime

import ormar

from db.database import ormar_config


class Member(ormar.Model):
    ormar_config = ormar_config.copy(tablename="members")

    id: int = ormar.Integer(primary_key=True, autoincrement=True)
    user_id: int = ormar.BigInteger(unique=True)
    messages_count: int = ormar.Integer(default=0)
    reputation_points: int = ormar.Integer(default=0)
    date: datetime = ormar.DateTime(default=datetime.now)

    violations_count_profanity: int = ormar.Integer(default=0)
    violations_count_spam: int = ormar.Integer(default=0)

    halloween_sweets: int = ormar.Integer(default=0)
    halloween_golden_tickets: int = ormar.Integer(default=0)
