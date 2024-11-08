import ormar
from models.member import Member

import cachetools
from cachetools import LRUCache
from functools import wraps

# Create LRU-cache with size of 1000 elements
# TODO: Make this cache system to work when bot is used in multiple chats
# (currently it's for 1 chat only)
members_cache = LRUCache(maxsize=1000)
tgmembers_cache = LRUCache(maxsize=1000)


def cache_async_tgmembers(func):
    @wraps(func)
    async def wrapper(bot, chat_id, user_id):
        # check if it's in cache already
        if user_id in tgmembers_cache:
            return tgmembers_cache[user_id]

        # Call function and cache result
        result = await func(bot, chat_id, user_id)
        tgmembers_cache[user_id] = result
        return result

    return wrapper


@cache_async_tgmembers
async def retrieve_tgmember(bot, chat_id, user_id):
    return await bot.get_chat_member(chat_id, user_id)


def cache_async_members(func):
    @wraps(func)
    async def wrapper(user_id):
        # check if it's in cache already
        if user_id in members_cache:
            return members_cache[user_id]

        # Call function and cache result
        result = await func(user_id)
        members_cache[user_id] = result
        return result

    return wrapper


@cache_async_members
async def retrieve_or_create_member(user_id):
    member = None

    try:
        member = await Member.objects.get(user_id=user_id)
    except ormar.NoMatch:
        member = await Member.objects.create(user_id=user_id, messages_count=1)
    finally:
        return member