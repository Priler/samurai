"""
Profanity detection service using censure library.
"""
from dataclasses import dataclass
import re
from typing import Iterable, Mapping, NamedTuple
import unicodedata

from config import config
from libs.censure import Censor

# Create censor instances for different languages
censor_ru = Censor.get(lang='ru')
censor_en = Censor.get(lang='en')


class CensureLineResult(NamedTuple):
    cleaned_text: str
    bad_words_count: int
    bad_phrases_count: int
    detected_bad_words: list[str]
    detected_bad_phrases: list[str]
    detected_patterns: list[object]


class ProfanityCheckResult(NamedTuple):
    detected: bool
    word: str | None
    line: CensureLineResult


@dataclass(frozen=True, slots=True)
class ProfanityMatch:
    text: str
    normalized: str
    start: int
    end: int
    language: str
    reason: str
    pattern: str | None = None


_CENSORS = {
    "ru": censor_ru,
    "russian": censor_ru,
    "en": censor_en,
    "english": censor_en,
}

_LANG_ALIASES = {"ru": "ru", "russian": "ru", "en": "en", "english": "en"}
_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)

# substitutions commonly used to evade English filters
_EN_CONFUSABLES = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x",
    "у": "y", "к": "k", "м": "m", "т": "t", "в": "b", "н": "h",
    "і": "i", "ј": "j",
    "0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t",
    "@": "a", "$": "s",
})

# reverse direction: Latin lookalikes folded to Cyrillic, so bait words typed
# as "пoрнo" (Latin o) still match the Cyrillic blacklist
_RU_CONFUSABLES = str.maketrans({
    "a": "а", "e": "е", "o": "о", "p": "р", "c": "с", "x": "х",
    "y": "у", "k": "к", "m": "м", "t": "т", "b": "в", "h": "н",
    "0": "о", "3": "е", "4": "а",
})

# separators spammers wedge between letters ("п.о.р.н.о", "s e x")
_NAME_SEPARATORS_RE = re.compile(r"[\s._\-*|/\\+~^'\"`,:;!?()\[\]{}]+")


def normalize_text(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    text = unicodedata.normalize("NFKC", text)
    return "".join(char for char in text if unicodedata.category(char) != "Cf")


def normalize_for_detection(text: str, lang: str) -> str:
    canonical_lang = _canonical_language(lang)
    normalized = normalize_text(text).casefold()
    if canonical_lang == "en":
        normalized = normalized.translate(_EN_CONFUSABLES)
    return normalized


def _normalize_with_offsets(text: str, lang: str) -> tuple[str, list[int]]:
    output: list[str] = []
    offsets: list[int] = []
    for index, char in enumerate(text):
        normalized_char = unicodedata.normalize("NFKC", char)
        normalized_char = "".join(
            item for item in normalized_char if unicodedata.category(item) != "Cf"
        ).casefold()
        if lang == "en":
            normalized_char = normalized_char.translate(_EN_CONFUSABLES)
        output.extend(normalized_char)
        offsets.extend([index] * len(normalized_char))
    return "".join(output), offsets


def _canonical_language(lang: str) -> str:
    try:
        return _LANG_ALIASES[lang.lower()]
    except (AttributeError, KeyError) as exc:
        raise ValueError(f"Unsupported profanity language: {lang!r}") from exc


def _configured_allowlist(lang: str) -> frozenset[str]:
    words = config.profanity.allowlist_ru if lang == "ru" else config.profanity.allowlist_en
    return frozenset(normalize_for_detection(word, lang) for word in words)


def _mask_allowlisted_words(text: str, lang: str, allowlist: Iterable[str]) -> str:
    normalized_allowlist = {
        normalize_for_detection(word, lang) for word in allowlist if word
    }
    if not normalized_allowlist:
        return text

    chars = list(text)
    for match in _WORD_RE.finditer(text):
        if match.group() in normalized_allowlist:
            chars[match.start():match.end()] = " " * (match.end() - match.start())
    return "".join(chars)


def prepare_word(word: str) -> str:
    """Prepare word for profanity checking."""
    word = normalize_text(word).lower().strip()
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


def check_for_profanity(
    text: str,
    lang: str = "ru",
    *,
    allowlist: Iterable[str] | None = None,
) -> ProfanityCheckResult:
    """
    Check text for profanity in specified language.

    Returns:
        Tuple of (is_profanity_detected, detected_word, line_info)
    """
    canonical_lang = _canonical_language(lang)
    censor = _CENSORS[canonical_lang]
    normalized = normalize_for_detection(text, canonical_lang)
    normalized = _mask_allowlisted_words(
        normalized,
        canonical_lang,
        _configured_allowlist(canonical_lang) if allowlist is None else allowlist,
    )
    line_info = CensureLineResult(*censor.clean_line(normalized))
    if line_info.bad_words_count:
        return ProfanityCheckResult(True, line_info.detected_bad_words[0], line_info)
    if line_info.bad_phrases_count:
        return ProfanityCheckResult(True, line_info.detected_bad_phrases[0], line_info)

    # check_line joins suspicious short fragments (for example "sh it") and
    # stops at the first match, covering spacing evasions cheaply.
    detection = censor.check_line(normalized)
    if detection["is_good"]:
        return ProfanityCheckResult(False, None, line_info)

    word_info = detection.get("bad_word_info")
    if word_info:
        word = word_info["word"]
        line_info = CensureLineResult(
            normalized, 1, 0, [word], [], list(word_info["accuse"])
        )
    else:
        patterns = list(detection.get("accuse", []))
        word = normalized
        line_info = CensureLineResult(normalized, 0, 1, [], [word], patterns)
    return ProfanityCheckResult(True, word, line_info)


def find_profanity(
    text: str,
    languages: Iterable[str] = ("ru", "en"),
    *,
    allowlists: Mapping[str, Iterable[str]] | None = None,
) -> tuple[ProfanityMatch, ...]:
    """Return explainable first matches for each requested language."""
    matches: list[ProfanityMatch] = []
    for requested_lang in languages:
        lang = _canonical_language(requested_lang)
        language_allowlist = None if allowlists is None else allowlists.get(lang)
        result = check_for_profanity(text, lang, allowlist=language_allowlist)
        if not result.detected or result.word is None:
            continue

        detection_text, source_offsets = _normalize_with_offsets(text, lang)
        needle = normalize_for_detection(result.word, lang)
        normalized_start = detection_text.find(needle)
        if normalized_start < 0:
            # Fragment joining changes the comparison form; identify the smallest
            # original token run that independently reproduces the detection.
            start, end = 0, len(text)
            reason = "fragmented"
        else:
            normalized_end = normalized_start + len(needle)
            start = source_offsets[normalized_start]
            end = source_offsets[normalized_end - 1] + 1
            reason = "phrase" if result.line.bad_phrases_count else "word"

        pattern = result.line.detected_patterns[0] if result.line.detected_patterns else None
        matches.append(ProfanityMatch(
            text=text[start:end],
            normalized=needle,
            start=start,
            end=end,
            language=lang,
            reason=reason,
            pattern=str(pattern) if pattern is not None else None,
        ))

    return tuple(matches)


def check_for_profanity_all(text: str) -> tuple[bool, str | None]:
    """
    Check text for profanity in all supported languages.

    Returns:
        Tuple of (is_profanity_detected, detected_word)
    """
    for lang in ("ru", "en"):
        detected, word, _ = check_for_profanity(text, lang=lang)
        if detected:
            return True, word
    return False, None


# Blacklist words spam accounts put in display names.
# Matched as substrings against a confusable-normalized name, so "p0rn" / "пoрно" (mixed script) are covered.
_NAME_BLACKLIST_RU = (
    "профил",
    "посмотри",
    "кликай",
    "загляни",
    "порн",
    "секс",
    "интим",
    "эротик",
    "вебкам",
    "шлюх",
    "проститу",
    "разврат",
    "голая",
    "голые",
    "инцест",
    "сучка",
    "мамка",
)

_NAME_BLACKLIST_EN = (
    "porn",
    "xxx",
    "18+",
    "sex",
    "nude",
    "naked",
    "onlyfans",
    "webcam",
    "escort",
    "hookup",
    "milf",
    "fuckme",
    "cam4",
    "hentai",
)


def check_name_for_violations(name: str) -> bool:
    """
    Check if a name contains violations (blacklisted words or profanity).

    Returns:
        True if name is clean, False if it contains violations.
    """
    if not name:
        return True

    # Two passes: the EN pass folds Cyrillic lookalikes to Latin, so Latin bait
    # tokens survive script mixing; the RU pass folds the other direction.
    checks = (
        (normalize_for_detection(name, "en"),
         _NAME_BLACKLIST_EN + tuple(config.spam.name_blacklist_en)),
        (normalize_for_detection(name, "ru").translate(_RU_CONFUSABLES),
         _NAME_BLACKLIST_RU + tuple(config.spam.name_blacklist_ru)),
    )

    for normalized, blacklist in checks:
        collapsed = _NAME_SEPARATORS_RE.sub("", normalized)
        for token in blacklist:
            # Anchor at a word start so bait words still match with any suffix
            # ("порнуха", "sexchat") without firing on Middlesex or Профессор.
            pattern = re.compile(r"\b" + re.escape(token.casefold()))
            if pattern.search(normalized) or pattern.search(collapsed):
                return False

    profanity_detected, _ = check_for_profanity_all(name)

    return not profanity_detected
