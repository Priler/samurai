import os
is_heroku = os.environ.get('IS_HEROKU', None)

if is_heroku:
    from configurator import config

    # override config with heroku env vars
    config.bot.owner = int(os.environ.get('BOT_OWNER', None))
    config.bot.token = os.environ.get('BOT_TOKEN', None)

    config.groups.main = int(os.environ.get('GROUPS_MAIN', None))
    config.groups.reports = int(os.environ.get('GROUPS_REPORTS', None))
    config.groups.logs = int(os.environ.get('GROUPS_LOGS', None))
    config.groups.linked_channel = int(os.environ.get('LINKED_CHANNEL', None))

    config.db.url = str(os.environ.get('DB_URL', None))