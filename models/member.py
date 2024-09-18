import ormar
from db import ormar_config

class Member(ormar.Model):
    ormar_config = ormar_config.copy(tablename="members")

    id: int = ormar.Integer(primary_key=True, auto_increment=True)
    user_id: int = ormar.BigInteger(unique=True)
    messages_count: int = ormar.Integer()