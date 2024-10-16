import logging

from aiogram import Bot, Dispatcher

from configurator import config, make_config
from filters import IsAdminFilter, MemberCanRestrictFilter, IsOwnerFilter

# Configure logging
logging.basicConfig(level=logging.INFO)

if not make_config("config.ini"):
    logging.error("Errors while parsing config file. Exiting.")
    exit(1)

import heroku_config

if not config.bot.token:
    logging.error("No token provided")
    exit(1)

# Initialize bot and dispatcher
bot = Bot(token=config.bot.token, parse_mode="HTML")
dp = Dispatcher(bot)
dp.message_handlers.once = False

# Activate filters
dp.filters_factory.bind(IsAdminFilter)
dp.filters_factory.bind(IsOwnerFilter)
dp.filters_factory.bind(MemberCanRestrictFilter)
