import asyncio

from configurator import config

from typing import Optional

import databases
import pydantic

import ormar
import sqlalchemy
from sqlalchemy.ext.asyncio import create_async_engine

# create db config
DATABASE_URL = config.db.url
ormar_config = ormar.OrmarConfig(
    database=databases.Database(DATABASE_URL),
    metadata=sqlalchemy.MetaData(),
    engine=create_async_engine(DATABASE_URL, echo=True),
)