import datetime
import sys
import time
import typing
from typing import final
from enum import Enum
import re
import unicodedata

import psutil

import localization
from configurator import config

sys.path.append("./libs")  # allow module import from git submodules

from libs.gender_extractor import GenderExtractor
g_ext = GenderExtractor()

class Gender(Enum):
    UNKNOWN = 0
    MALE = 1
    FEMALE = 2
    AMBIGUOUS = 3 # can be both female & male

from libs.censure import Censor

# create censor instances
censor_ru = Censor.get(lang='ru')
censor_en = Censor.get(lang='en')


def prepare_word(word):
    word = word.lower()
    word = word.strip()  # just to make sure it's as clean as possible
    return censor_ru.prepare_word(word)


def check_name_for_violations(name) -> bool:
    blacklist_words = [
        "профиль",
        "посмотри",
        "кликай",
        "загляни",
        "проф"
    ]

    name = prepare_word(name)
    is_clean = not any(sub.lower() in name.lower() for sub in blacklist_words)

    _prof = check_for_profanity(name, detect_name_language(name))

    return not _prof[0] and is_clean


def check_for_profanity(text, lang="ru"):
    _profanity_detected = False
    _word = None

    if lang == "ru" or lang == "russian":
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


def detect_gender__compare(name: str, country: str = None) -> Gender:
    try:
        if country is not None:
            r = g_ext.extract_gender(name, country)
        else:
            r = g_ext.extract_gender(name)
    except ValueError:
        # assume gender unknown if it cannot be extracted
        return Gender.UNKNOWN

    if 'female and male' in r:
        return Gender.AMBIGUOUS 
    elif 'female' in r:
        return Gender.FEMALE
    elif 'male' in r:
        return Gender.MALE
    else:
        return Gender.UNKNOWN


def remove_non_letters(text: str) -> str:
    # but preserve spaces and digits
    return ''.join(char for char in text if char.isalpha() or char == ' ' or char.isdigit())


def name_norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s.lower())
    s = s.replace("ё", "е")
    s = re.sub(r"[^а-яa-z]+", "", s)        # убираем цифры/эмодзи/знаки
    s = re.sub(r"(.)\1{2,}", r"\1\1", s)    # сжать растяжки: оооляя -> ооля
    return s


def name_strip_suffixes(name: str, suffixes: list) -> str:
    for suf in sorted(suffixes, key=len, reverse=True):
        if name.endswith(suf) and len(name) - len(suf) >= 3:
            return name[: -len(suf)]
    return name


def remove_emojis(text):
    emoji_pattern = re.compile(
        "[\U0001F600-\U0001F64F"  # Смайлы
        "\U0001F300-\U0001F5FF"  # Символы и пиктограммы
        "\U0001F680-\U0001F6FF"  # Транспорт и символы карт
        "\U0001F1E0-\U0001F1FF"  # Флаги (составные символы)
        "\U00002700-\U000027BF"  # Разные символы
        "\U000024C2-\U0001F251"  # Дополнительные символы
        "]+", flags=re.UNICODE)

    return emoji_pattern.sub(r'', text)


def detect_name_language(name):
    """
    Detects if a name is written in Russian or English.

    Args:
        name (str): Name to check

    Returns:
        str: 'russian' if name contains Russian characters, 'english' if only English characters,
             'unknown' if contains neither or mixed
    """
    russian_chars = set('абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ')
    english_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ')

    russian_count = sum(1 for char in name if char in russian_chars)
    english_count = sum(1 for char in name if char in english_chars)

    total_letters = russian_count + english_count

    if total_letters == 0:
        return 'unknown'
    # elif russian_count > 0 and english_count == 0:
    elif russian_count > english_count:
        return 'russian'
    # elif english_count > 0 and russian_count == 0:
    elif english_count > russian_count:
        return 'english'
    else:
        return 'unknown'


def transliterate_name(name, force_lang = None):
    """
    Transliterates names between Russian and English based on automatic language detection.

    Args:
        name (str): Name in Russian or English

    Returns:
        str: Transliterated name in the opposite language
        None: If language detection fails or input is invalid
    """
    # Translation dictionaries
    ru_to_en = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd',
        'е': 'e', 'ё': 'e', 'ж': 'zh', 'з': 'z', 'и': 'i',
        'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n',
        'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't',
        'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch',
        'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '',
        'э': 'e', 'ю': 'yu', 'я': 'ya',
        'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D',
        'Е': 'E', 'Ё': 'E', 'Ж': 'Zh', 'З': 'Z', 'И': 'I',
        'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M', 'Н': 'N',
        'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T',
        'У': 'U', 'Ф': 'F', 'Х': 'Kh', 'Ц': 'Ts', 'Ч': 'Ch',
        'Ш': 'Sh', 'Щ': 'Sch', 'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya'
    }

    # Create reverse mapping (English to Russian)
    en_to_ru = {}
    for ru, en in ru_to_en.items():
        if len(en) == 1:  # Single character mappings
            en_to_ru[en.lower()] = ru.lower()
            en_to_ru[en.upper()] = ru.upper()
        else:  # Multi-character mappings like 'zh', 'ch'
            en_to_ru[en.lower()] = ru.lower()
            en_to_ru[en.title()] = ru.upper()

    if not force_lang:
        # Detect language
        lang = detect_name_language(name)

        if lang == 'unknown':
            return None
    else:
        lang = force_lang

    if lang == 'russian':
        # Russian to English
        result = ''
        for char in name:
            result += ru_to_en.get(char, char)
        return result
    else:
        # English to Russian
        result = ''
        i = 0
        while i < len(name):
            # Try to match two characters first (for 'zh', 'ch', etc.)
            if i < len(name) - 1:
                two_chars = name[i:i + 2]
                if two_chars.lower() in ['zh', 'kh', 'ts', 'ch', 'sh', 'yu', 'ya']:
                    result += en_to_ru.get(two_chars.title() if two_chars[0].isupper() else two_chars.lower(),
                                           two_chars)
                    i += 2
                    continue
                elif two_chars.lower() == 'sc' and i < len(name) - 2 and name[i:i + 3].lower() == 'sch':
                    # Handle 'sch' case
                    result += en_to_ru.get('Sch' if two_chars[0].isupper() else 'sch', 'sch')
                    i += 3
                    continue

            # Single character conversion
            char = name[i]
            result += en_to_ru.get(char, char)
            i += 1

        return result


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
    I don't want to use hardcoded chat username, so I just take its ID (see groups.main in config),
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
                    return int(float(line.split(':')[1].strip()))
    except:
        return "N/A"
    return "N/A"


# usage example: detect_gender = measure_execution(detect_gender, "detect_gender")
# detect_gender("name")
def measure_execution(func, name):
    def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        execution_time = (end_time - start_time) * 1000  # Convert to milliseconds
        print(f"{name} took {execution_time:.3f} ms")
        return result
    return wrapper

