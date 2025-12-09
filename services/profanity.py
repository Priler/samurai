"""
Profanity detection service using censure library.
"""
import sys
import re
import unicodedata

# Add libs path for censure module
sys.path.insert(0, "./libs")

from libs.censure import Censor

# Create censor instances for different languages
censor_ru = Censor.get(lang='ru')
censor_en = Censor.get(lang='en')


def prepare_word(word: str) -> str:
    """Prepare word for profanity checking."""
    word = word.lower()
    word = word.strip()
    return censor_ru.prepare_word(word)


def detect_name_language(name: str) -> str:
    """
    Detects if a name is written in Russian or English.

    Returns:
        'russian', 'english', or 'unknown'
    """
    russian_chars = set('абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ')
    english_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ')

    russian_count = sum(1 for char in name if char in russian_chars)
    english_count = sum(1 for char in name if char in english_chars)

    total_letters = russian_count + english_count

    if total_letters == 0:
        return 'unknown'
    elif russian_count > english_count:
        return 'russian'
    elif english_count > russian_count:
        return 'english'
    else:
        return 'unknown'


def check_for_profanity(text: str, lang: str = "ru") -> tuple[bool, str | None, tuple]:
    """
    Check text for profanity in specified language.

    Returns:
        Tuple of (is_profanity_detected, detected_word, line_info)
    """
    _profanity_detected = False
    _word = None

    if lang == "ru" or lang == "russian":
        line_info = censor_ru.clean_line(text)
    else:
        line_info = censor_en.clean_line(text)

    # line_info: (line, bad_words_count, bad_phrases_count, detected_bad_words, detected_bad_phrases)

    if line_info[1] or line_info[2]:
        if line_info[1]:
            _word = line_info[3][0]
        else:
            _word = line_info[4][0]

        _profanity_detected = True

    return _profanity_detected, _word, line_info


def check_for_profanity_all(text: str) -> tuple[bool, str | None]:
    """
    Check text for profanity in all supported languages.

    Returns:
        Tuple of (is_profanity_detected, detected_word)
    """
    _del = False
    _word = None

    # Check for RUSSIAN
    _del, _word, _ = check_for_profanity(text, lang="ru")

    if not _del:
        # Check for ENGLISH
        _del, _word, _ = check_for_profanity(text, lang="en")

    return _del, _word


def check_name_for_violations(name: str) -> bool:
    """
    Check if a name contains violations (blacklisted words or profanity).

    Returns:
        True if name is clean, False if it contains violations.
    """
    blacklist_words = [
        "профиль",
        "посмотри",
        "кликай",
        "загляни",
        "проф"
    ]

    prepared_name = prepare_word(name)
    is_clean = not any(sub.lower() in prepared_name.lower() for sub in blacklist_words)

    profanity_detected, _, _ = check_for_profanity(prepared_name, detect_name_language(name))

    return not profanity_detected and is_clean
