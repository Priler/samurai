import asyncio
import functools
import logging

import databases
import ormar
import sqlalchemy
from sqlalchemy.ext.asyncio import create_async_engine

from config import config

try:
    from pymysql.err import InterfaceError, OperationalError
except ImportError:
    _MYSQL_ERRORS = ()
else:
    _MYSQL_ERRORS = (OperationalError, InterfaceError)

logger = logging.getLogger(__name__)

DATABASE_URL = config.db.url

# aiomysql pool options
_db_options = {}
if DATABASE_URL.startswith("mysql"):
    _db_options = {
        "min_size": 1,
        "max_size": 10,
        "pool_recycle": 1800,  # seconds; must stay below MySQL wait_timeout
    }

ormar_config = ormar.OrmarConfig(
    database=databases.Database(DATABASE_URL, **_db_options),
    metadata=sqlalchemy.MetaData(),
    engine=create_async_engine(DATABASE_URL),
)

# MySQL "connection lost" error codes
#   2006 = CR_SERVER_GONE_ERROR, 2013 = CR_SERVER_LOST
_TRANSIENT_DB_CODES = {2006, 2013}


def _is_transient_db_error(exc: Exception) -> bool:
    if isinstance(exc, _MYSQL_ERRORS):
        code = exc.args[0] if exc.args else None
        return code in _TRANSIENT_DB_CODES
    # WinError 121 etc. surface as a bare OSError underneath.
    return isinstance(exc, OSError)


def db_retry(retries: int = 3, delay: float = 0.5):
    """
    Retry a DB coroutine on transient "connection lost" errors.
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    if not _is_transient_db_error(exc):
                        raise
                    last_exc = exc
                    logger.warning(
                        "Transient DB error in %s (attempt %d/%d): %s",
                        func.__name__, attempt, retries, exc,
                    )
                    if attempt < retries:
                        await asyncio.sleep(delay * attempt)
                        # A dropped link can also tear down the whole pool. Re-
                        # establish it before the next attempt so we don't just
                        # retry into a disconnected Database.
                        await _ensure_connected()
            raise last_exc

        return wrapper

    return decorator


async def _ensure_connected() -> None:
    """Reconnect the database if the connection was lost."""
    if not ormar_config.database.is_connected:
        try:
            await ormar_config.database.connect()
            logger.info("Reconnected to database")
        except Exception as exc:
            logger.warning("DB reconnect failed: %s", exc)


async def init_db() -> None:
    if not ormar_config.database.is_connected:
        await ormar_config.database.connect()


async def close_db() -> None:
    if ormar_config.database.is_connected:
        await ormar_config.database.disconnect()
