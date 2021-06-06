# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import re
import random
import string
from unittest import TestCase as CoreTestCase
from importlib import import_module

from censure.base import Censor, CensorException
from censure.lang.common import constants, patterns
# from censure.tests.data import (
#     SIMPLE_OBSCENE_WORDS, E_OBSCENE_WORDS, PI_OBSCENE_WORDS,
#     OBSCENE_HTML_LINES,
# )

RUSSIAN_LOWERCASE = 'абвгдеёжзиклмнопрстуфхцчшщъьэюя'
ENGLISH_LOWERCASE = string.ascii_lowercase
ALL_LOWERCASE = ENGLISH_LOWERCASE + RUSSIAN_LOWERCASE


class TestCase(CoreTestCase):
    @classmethod
    def _get_random_word_base(
            cls, letters=None, min_chars=3, max_chars=10, assert_good=True, russian_only=False):
        letters = letters or ENGLISH_LOWERCASE
        word = ''.join((random.choice(letters) for _ in range(min_chars, max_chars)))
        if assert_good:
            if not cls.censor.check_word(word)['is_good']:
                word = cls._get_random_word(min_chars=min_chars, max_chars=max_chars)
        return word

    @classmethod
    def _get_random_count(cls, min_i=2, max_i=10):
        return random.randint(min_i, max_i)

    @classmethod
    def _dice(cls):
        # binary choice
        return random.choice((True, False))


class TestCaseRu(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.censor = Censor.get(lang='ru', do_compile=False)
        cls.data = import_module('censure.tests.ru.data')

    @classmethod
    def _get_random_word(cls, min_chars=3, max_chars=10, assert_good=True,
                         russian_only=False):
        letters = RUSSIAN_LOWERCASE if russian_only else ALL_LOWERCASE
        return cls._get_random_word_base(
            min_chars=min_chars, max_chars=max_chars, assert_good=assert_good, letters=letters)


class TestCaseEn(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.censor = Censor.get(lang='en', do_compile=False)
        cls.data = import_module('censure.tests.en.data')

    @classmethod
    def _get_random_word(cls, min_chars=3, max_chars=10, assert_good=True):
        letters = ENGLISH_LOWERCASE
        return cls._get_random_word_base(
            min_chars=min_chars, max_chars=max_chars, assert_good=assert_good, letters=letters)


__all__ = [
    'random', 're',
    'TestCase', 'TestCaseRu', 'TestCaseEn', 'CoreTestCase',

    'Censor', 'CensorException',
    'constants', 'patterns',

    # 'SIMPLE_OBSCENE_WORDS', 'E_OBSCENE_WORDS', 'PI_OBSCENE_WORDS',
    # 'OBSCENE_HTML_LINES',
    # 'BEEP'
]
