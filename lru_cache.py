import ormar
from models.member import Member
import re

from utils import Gender, remove_non_letters, detect_name_language, detect_gender__compare, transliterate_name, name_strip_suffixes, name_norm

import cachetools
from cachetools import LRUCache
from functools import wraps

# Create LRU-cache with size of 1000 elements
# TODO: Make this cache system to work when bot is used in multiple chats
# (currently it's for 1 chat only)
members_cache = LRUCache(maxsize=1000)
tgmembers_cache = LRUCache(maxsize=1000)
gender_detections_cache = LRUCache(maxsize=1000)

def cache_gender_detection(func):
    @wraps(func)
    def wrapper(name):
        # check if it's in cache already
        if name in gender_detections_cache:
            return gender_detections_cache[name]

        # Call function and cache result
        result = func(name)
        gender_detections_cache[name] = result
        return result

    return wrapper


@cache_gender_detection
def detect_gender(name: str) -> Gender:
    # remove any non-letters (emoji etc)
    _name = name
    name = remove_non_letters(name)

    FEMALE_SUFFIXES = [
        "очка", "ечка", "юшка", "енька", "инка", "ушка", "ка", "ша", "уся", "юся", "ся",
        "онька", "ень", "еньки", "юнька",
    ]

    MALE_SUFFIXES = [
        "ик", "ек", "ёк", "ок", "чик",
        "яша", "юша", "ёша", "ян"
    ]

    # pre-process the name
    if name:
        try:
            name = name.lower()
            name = next((element for element in name.split(" ") if element.strip()), None) # get first name
            name = name.strip() # just to make sure it's as clean as possible

        except AttributeError:
            name = _name # restore OG
    else:
        name = _name # restore OG name (nicknames like "." or "$" etc)

    #print(name)
    #print(len(name))

    # compare
    _name_lang = detect_name_language(name)

    # print(name)
    # print(_name_lang)

    if _name_lang == 'russian':
        det_gen = detect_gender__compare(name, "Russia")

        if det_gen == Gender.UNKNOWN:
            # dedup letters and try again
            dedupped_name = re.sub(r'([А-Яа-яЁё])\1+', r'\1', name)
            det_gen = detect_gender__compare(dedupped_name, "Russia")

            if det_gen == Gender.UNKNOWN:
                # try to detect based on suffixes
                # and try/detect again
                name = name_norm(name)

                if name != name_strip_suffixes(name, FEMALE_SUFFIXES):
                    det_gen = Gender.FEMALE
                elif name != name_strip_suffixes(name, MALE_SUFFIXES):
                    det_gen = Gender.MALE

                # print("SSS ", name)
                # print("SSS ", det_gen)

                # det_gen = detect_gender__compare(name, "Russia")

                if det_gen == Gender.UNKNOWN:
                    # if gender is still unknown, try to transliterate it and compare again

                    det_gen = detect_gender__compare(transliterate_name(name), "USA")

    elif _name_lang == 'english':
        det_gen = detect_gender__compare(name, "USA")

        # if gender unknown, try to transliterate it and compare again
        if det_gen == Gender.UNKNOWN:
            det_gen = detect_gender__compare(transliterate_name(name), "Russia")

    else:
        det_gen = detect_gender__compare(name)

    # return result, whatever it will be
    return det_gen
    # last shot
    # if name ends with 'а' letter, then assume it's female
    # return Gender.FEMALE if name not in ["фома", "савва", "кима", "алима"] and name.lower()[-1] == 'а' else Gender.UNKNOWN

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
