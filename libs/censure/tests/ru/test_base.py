# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from censure.tests.base import *

from censure.base import _get_token_value, _get_remained_tokens, Censor


class CensorInternalsTestCase(TestCaseRu):
    def test__is_pi_or_e_word(self):
        for w, result in (
            ('2.72', True),
            ('3.14', True),
            ('2.71', False),
            ('3.15', False),
            ('5.15', False),
        ):
            if self._dice():  # prefix
                w = '{}{}'.format(self._get_random_word(), w)
            if self._dice():  # suffix
                w = '{}{}'.format(w, self._get_random_word())
            self.assertEqual(self.censor._is_pi_or_e_word(w), result)

    def test_good_word(self):
        for x in range(50):
            word = self._get_random_word(russian_only=True)
            word_info = self.censor.check_word(word)
            self.assertDictContainsSubset({
                # 'excuse': [],
                # 'accuse': [],
                'word': self.censor._prepare_word(word),
                'is_good': True,
            }, word_info)

    def test_check_e_word(self):
        word = self.data.E_OBSCENE_WORDS[0]
        word_info = self.censor.check_word(word)
        self.assertDictContainsSubset({
            'excuse': [],
            'word': self.censor._prepare_word(word),
            'is_good': False,
        }, word_info)
        self.assertTrue(len(word_info.get('accuse', [])) > 0)

    def test_clean_line_e_word(self):
        word = self.data.E_OBSCENE_WORDS[0]
        cleaned_line, count, phrases_count, _, _, _ = self.censor.clean_line(word)
        self.assertEqual(cleaned_line, constants.BEEP)
        self.assertEqual(count, 1)
        self.assertEqual(phrases_count, 0)
