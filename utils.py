import datetime
import sys
import typing
from typing import final
from enum import Enum

import psutil

import localization
from configurator import config

from gender_extractor import GenderExtractor
g_ext = GenderExtractor()

class Gender(Enum):
    UNKNOWN = 0
    MALE = 1
    FEMALE = 2

sys.path.append("./censure")  # allow module import from git submodule
from censure import Censor

# create censor instances
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


def detect_gender(name: str) -> Gender:
    # pre-process the name
    name = name.split(" ")[0]
    name = name.strip()

    # extract
    r = g_ext.extract_gender(name)

    # return result
    if 'female' in r:
        return Gender.FEMALE
    elif 'male' in r:
        return Gender.MALE
    else:
        # last shot
        # if name ends with 'а' letter, then assume it's female
        return Gender.FEMALE if name not in ["фома", "савва", "кима", "алима"] and name.lower()[-1] == 'а' else Gender.UNKNOWN


def user_mention(from_user):
    _s = from_user.full_name

    if from_user.full_name != from_user.mention:
        _s += " (" + from_user.mention + ")"
    else:
        _s += " (<a href=\"" + from_user.url + "\">id" + str(from_user.id) + "</a>)"

    return _s


def generate_log_message(message, log_type="default"):
    now = datetime.datetime.now()
    current_time = now.strftime("%H:%M:%S")

    log_message = "🕥 <i>" + current_time + "</i> <b>[" + log_type.upper() + "]</b> "
    log_message += message

    return log_message


async def write_log(bot, message, log_type="default"):
    return await bot.send_message(config.groups.logs, generate_log_message(message, log_type))


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
    return abs(chat_id + 1_000_000_000_000)


def remove_prefix(text, prefix):
    if text.startswith(prefix):
        return text[len(prefix):]
    return text  # or whatever


def get_cpu_freq():
    try:
        freq = psutil.cpu_freq()
        return freq.max if freq and freq.max > 0 else "N/A"
    except Exception:
        return "N/A"


def get_cpu_freq_from_proc():
    try:
        with open('/proc/cpuinfo') as f:
            for line in f:
                if line.startswith('cpu MHz'):
                    return float(line.split(':')[1].strip())
    except:
        return "N/A"
    return "N/A"
