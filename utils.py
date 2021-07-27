import datetime
import sys
import typing

import localization
from configurator import config

sys.path.append("./censure")  # allow module import from git submodule

from censure import Censor

censor_ru = Censor.get(lang='ru')
censor_en = Censor.get(lang='en')

def check_for_profanity(text, lang="ru"):
    _profanity_detected = False
    _word = None

    if lang == "ru":
        line_info = censor_ru.clean_line(text)
    else:
        line_info = censor_en.clean_line(text)

    # line, bad_words_count, bad_phrases_count, detected_bad_words, detected_bad_phrases

    # check
    if line_info[1] or line_info[2]:
        if line_info[1]:
            _word = line_info[3][0]
        else:
            _word = line_info[4][0]

        _profanity_detected = True

    return _profanity_detected, _word, line_info


def check_for_profanity_all(text):
    _del = False
    _word = None
    _line = None

    # Check for RUSSIAN
    _del, _word, _line = check_for_profanity(text, lang="ru")

    if not _del:
        # Check for ENGLISH
        _del, _word, _line = check_for_profanity(text, lang="en")

    return _del, _word


def user_mention(from_user):
    _s = from_user.full_name

    if from_user.full_name != from_user.mention:
        _s += " (" + from_user.mention + ")"
    else:
        _s += " (<a href=\"" + from_user.url + "\">id" + str(from_user.id) + "</a>)"

    return _s


async def write_log(bot, message, log_type="default"):
    now = datetime.datetime.now()
    current_time = now.strftime("%H:%M:%S")

    log_message = "🕥 <i>" + current_time + "</i> <b>[" + log_type.upper() + "]</b> "
    log_message += message

    return await bot.send_message(config.groups.logs, log_message)


def get_restriction_time(string: str) -> typing.Optional[int]:
    """
    Get user restriction time in seconds

    :param string: string to check for multiplier. The last symbol should be one of:
        "m" for minutes, "h" for hours and "d" for days
    :return: number of seconds to restrict or None if error
    """
    if len(string) < 2:
        return None
    letter = string[-1]
    try:
        number = int(string[:-1])
    except TypeError:
        return None
    else:
        if letter == "m":
            return 60 * number
        elif letter == "h":
            return 3600 * number
        elif letter == "d":
            return 86400 * number
        else:
            return None


def get_report_comment(message_date: datetime.datetime, message_id: int, report_message: typing.Optional[str]) -> str:
    """
    Generates a report message for admins

    :param message_date: Datetime when reported message was sent
    :param message_id: ID of that message
    :param report_message: An optional note for admins so that they can understand what's wrong
    :return: A report message for admins in report chat
    """
    msg = localization.get_string("report_message").format(
        date=message_date.strftime(localization.get_string("report_date_format")),
        chat_id=get_url_chat_id(config.groups.main),
        msg_id=message_id)

    if report_message:
        msg += localization.get_string("report_note").format(note=report_message)
    return msg


def get_url_chat_id(chat_id: int) -> int:
    """
    Well, this value is a "magic number", so I have to explain it a bit.
    I don't want to use hardcoded chat username, so I just take its ID (see "group_main" variable above),
    add id_compensator and take a positive value. This way I can use https://t.me/c/{chat_id}/{msg_id} links,
    which don't rely on chat username.

    :param chat_id: chat_id to apply magic number to
    :return: chat_id for t.me links
    """
    return abs(int(chat_id) + 1_000_000_000_000)


def remove_prefix(text, prefix):
    if text.startswith(prefix):
        return text[len(prefix):]
    return text  # or whatever
