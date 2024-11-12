# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from censure.tests.base import *


class TestCensor(TestCaseEn):
    def test_on_simple_obscene_phrases(self):
        for words in (
                self.data.SIMPLE_OBSCENE_PHRASES,
        ):
            for line in words:
                cleaned_line, bad_words_count, bad_phrases_count, _, _, _ = self.censor.clean_line(line)
                self.assertEqual(cleaned_line, constants.BEEP)
                self.assertEqual(bad_phrases_count, 1)

    def test_on_simple_obscene_words(self):
        for words in (
                self.data.SIMPLE_OBSCENE_WORDS,
        ):
            for line in words:
                cleaned_line, bad_words_count, bad_phrases_count, _, _, _ = self.censor.clean_line(line)
                self.assertEqual(cleaned_line, constants.BEEP)
                self.assertEqual(bad_words_count, 1)

                count = self._get_random_count()
                line_template = ' '.join(('{line}' for _ in range(count)))
                line_repeated = line_template.format(line=line)
                cleaned_line, bad_words_count, bad_phrases_count, _, _, _ = self.censor.clean_line(line_repeated)
                self.assertEqual(cleaned_line, line_template.format(line=constants.BEEP))
                self.assertEqual(bad_words_count, count)
                self.assertEqual(bad_phrases_count, 0)

    def test_on_simple_html(self):
        for (html, cleaned_html) in self.data.OBSCENE_HTML_LINES:
            result, bad_words_count = self.censor.clean_html_line(html)
            self.assertTrue(bad_words_count > 0)
            self.assertEqual(result, cleaned_html)
