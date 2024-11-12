# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from censure.tests.base import *

from censure.base import _get_token_value, _get_remained_tokens, Censor


class CensorInternalsTestCase(TestCaseEn):
    def test_good_word(self):
        for x in range(50):
            word = self._get_random_word()
            word_info = self.censor.check_word(word)
            self.assertDictContainsSubset({
                'word': self.censor._prepare_word(word),
                'is_good': True,
            }, word_info)
