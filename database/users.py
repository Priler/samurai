from connection import conn
from queries import add_user


async def add(telg_id) -> None:
    await conn.execute(add_user, telg_id)
