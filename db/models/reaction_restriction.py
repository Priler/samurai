"""Persistent ownership of reaction restrictions imposed by the reputation policy."""
import ormar

from db.database import ormar_config


class ReactionRestriction(ormar.Model):
    ormar_config = ormar_config.copy(
        tablename="reaction_restrictions",
        constraints=[ormar.UniqueColumns("chat_id", "user_id")],
    )

    id: int = ormar.Integer(primary_key=True, autoincrement=True)
    chat_id: int = ormar.BigInteger(index=True)
    user_id: int = ormar.BigInteger(index=True)
