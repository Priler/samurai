"""
Gender detection service based on first name analysis.
"""
import sys
import re
import unicodedata
from enum import Enum

# Add libs path for gender_extractor module
sys.path.insert(0, "./libs")

from libs.gender_extractor import GenderExtractor

g_ext = GenderExtractor()


class Gender(Enum):
    UNKNOWN = 0
    MALE = 1
    FEMALE = 2
    AMBIGUOUS = 3  # Can be both female & male


def remove_non_letters(text: str) -> str:
    """Remove non-letters but preserve spaces and digits."""
    return ''.join(char for char in text if char.isalpha() or char == ' ' or char.isdigit())


def detect_name_language(name: str) -> str:
    """Detect if name is Russian or English."""
    russian_chars = set('абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ')
    english_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ')

    russian_count = sum(1 for char in name if char in russian_chars)
    english_count = sum(1 for char in name if char in english_chars)

    if russian_count + english_count == 0:
        return 'unknown'
    elif russian_count > english_count:
        return 'russian'
    elif english_count > russian_count:
        return 'english'
    return 'unknown'


def name_norm(s: str) -> str:
    """Normalize name for comparison."""
    s = unicodedata.normalize("NFKC", s.lower())
    s = s.replace("ё", "е")
    s = re.sub(r"[^а-яa-z]+", "", s)
    s = re.sub(r"(.)\1{2,}", r"\1\1", s)  # Compress repeated chars
    return s


def name_strip_suffixes(name: str, suffixes: list) -> str:
    """Strip diminutive suffixes from name."""
    for suf in sorted(suffixes, key=len, reverse=True):
        if name.endswith(suf) and len(name) - len(suf) >= 3:
            return name[: -len(suf)]
    return name


def transliterate_name(name: str, force_lang: str = None) -> str | None:
    """Transliterate name between Russian and English."""
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

    en_to_ru = {}
    for ru, en in ru_to_en.items():
        if len(en) == 1:
            en_to_ru[en.lower()] = ru.lower()
            en_to_ru[en.upper()] = ru.upper()
        else:
            en_to_ru[en.lower()] = ru.lower()
            en_to_ru[en.title()] = ru.upper()

    if not force_lang:
        lang = detect_name_language(name)
        if lang == 'unknown':
            return None
    else:
        lang = force_lang

    if lang == 'russian':
        result = ''
        for char in name:
            result += ru_to_en.get(char, char)
        return result
    else:
        result = ''
        i = 0
        while i < len(name):
            if i < len(name) - 1:
                two_chars = name[i:i + 2]
                if two_chars.lower() in ['zh', 'kh', 'ts', 'ch', 'sh', 'yu', 'ya']:
                    result += en_to_ru.get(two_chars.title() if two_chars[0].isupper() else two_chars.lower(), two_chars)
                    i += 2
                    continue
                elif two_chars.lower() == 'sc' and i < len(name) - 2 and name[i:i + 3].lower() == 'sch':
                    result += en_to_ru.get('Sch' if two_chars[0].isupper() else 'sch', 'sch')
                    i += 3
                    continue
            char = name[i]
            result += en_to_ru.get(char, char)
            i += 1
        return result


def detect_gender_compare(name: str, country: str = None) -> Gender:
    """Compare gender using gender_extractor library."""
    try:
        if country is not None:
            r = g_ext.extract_gender(name, country)
        else:
            r = g_ext.extract_gender(name)
    except ValueError:
        return Gender.UNKNOWN

    if 'female and male' in r:
        return Gender.AMBIGUOUS
    elif 'female' in r:
        return Gender.FEMALE
    elif 'male' in r:
        return Gender.MALE
    else:
        return Gender.UNKNOWN


def prepare_word(word: str) -> str:
    """Prepare word for analysis (fix masked letters)."""
    # Import here to avoid circular import
    sys.path.insert(0, "./libs")
    from libs.censure import Censor
    censor_ru = Censor.get(lang='ru')
    word = word.lower().strip()
    return censor_ru.prepare_word(word)


def detect_gender(name: str) -> Gender:
    """
    Detect gender from first name.

    Args:
        name: First name to analyze

    Returns:
        Gender enum value
    """
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

    # Pre-process the name
    if name:
        try:
            name = next(
                (part for part in name.split() if part.strip() and len(part.strip()) > 1),
                None
            )
        except AttributeError:
            name = _name
    else:
        name = _name

    # Preprocess name
    _name_lang = detect_name_language(name)
    name = prepare_word(name)
    name = transliterate_name(name, 'english' if _name_lang == 'russian' else 'english')

    if _name_lang == 'russian':
        det_gen = detect_gender_compare(name, "Russia")

        if det_gen == Gender.UNKNOWN:
            # Dedup letters and try again
            dedupped_name = re.sub(r'([А-Яа-яЁё])\1+', r'\1', name)
            det_gen = detect_gender_compare(dedupped_name, "Russia")

            if det_gen == Gender.UNKNOWN:
                # Try suffix-based detection
                name = name_norm(name)

                if name != name_strip_suffixes(name, FEMALE_SUFFIXES):
                    det_gen = Gender.FEMALE
                elif name != name_strip_suffixes(name, MALE_SUFFIXES):
                    det_gen = Gender.MALE

                if det_gen == Gender.UNKNOWN:
                    # Try transliteration
                    det_gen = detect_gender_compare(transliterate_name(name), "USA")

    elif _name_lang == 'english':
        det_gen = detect_gender_compare(name, "USA")

        if det_gen == Gender.UNKNOWN:
            det_gen = detect_gender_compare(transliterate_name(name), "Russia")
    else:
        det_gen = detect_gender_compare(name)

    return det_gen
