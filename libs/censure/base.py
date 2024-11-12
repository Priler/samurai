# -*- coding: utf-8 -*-
# Author:       masteroncluster@gmail.com
# Py-Censure is an obscene words detector/replacer for Russian / English languages

# Russian patterns are from PHP-Matotest, http://php-matotest.sourceforge.net/,
# that was written by Scarab
# Ported to Python by Master.Cluster <masteroncluster@gmail.com>, 2010, 2016
# English patters are adapted from http://www.noswearing.com/dictionary/

from __future__ import unicode_literals, print_function
import re
from copy import deepcopy
from importlib import import_module

from .lang.common import patterns, constants


def _get_token_value(token):
    return token.value


def _get_remained_tokens(tags_list):
    if not tags_list:
        return '', ''  # pre, post
    pre = []
    post = []
    body_pre = []
    body_post = []
    word_started = word_ended = False
    # <a><b>wo</b>rd<i> here</i><img><span>End</span>

    while len(tags_list):
        # pre and body
        tag = tags_list.pop(0)
        if tag.token_type == 'w':
            word_started = True

        if word_started:
            if tag.token_type in 'to tc ts':
                body_pre.append(tag)
        else:
            pre.append(tag)
        # post
        if len(tags_list):
            tag = tags_list.pop(-1)
            if tag.token_type == 'w':
                word_ended = True
            if word_ended:
                if tag.token_type in 'to tc ts':
                    body_post.insert(0, tag)
            else:
                post.insert(0, tag)

    body_tags = body_pre + body_post
    while len(body_tags):
        tag = body_tags.pop(0)
        if tag.token_type == 'sp':  # Do we need that tags?
            continue
        elif tag.token_type == 'tc':
            # can find in pre or in body
            open_tags = [x for x in pre if x.tag == tag.tag and x.token_type == 'to']
            if len(open_tags):
                pre.remove(open_tags[0])
                continue
        else:
            # can be in body
            close_tags = [x for x in body_tags if x.tag == tag.tag and x.token_type == 'tc']
            if len(close_tags):
                body_tags.remove(close_tags[0])
                continue
            # can find in post
            close_tags = [x for x in post if x.tag == tag.tag and x.token_type == 'tc']
            if len(close_tags):
                post.remove(close_tags[0])
                continue
    return ''.join(map(_get_token_value, pre + body_tags)), ''.join(map(_get_token_value, post))


class Token(object):
    def __init__(self, value=None, token_type=None):
        head = value.split(' ', 1)  # splits
        if len(head) == 1:
            # simple tag i.e <h1>, </i>
            head = head[0][1:-1].lower()  # need to cut last '>' symbol
        else:
            # complex tag with inner params i.e <input type=...>
            head = head[0].lower()[1:]

        if not token_type:
            token_type = 'to'   # open type ie <a...>
            # should derive from value
            if head[0] == '/':
                head = head[1:]
                token_type = 'tc'  # close type ie </a>
            elif value[-2] == '/':
                token_type = 'ts'  # self-closed type ie <img .../>

        if token_type in 'to tc ts' and \
                re.match(patterns.PAT_HTML_SPACE, value):  # token_type != w aka word
            token_type = 'sp'  # this is SPACER!!!

        self.value = value
        self.token_type = token_type  # w - word(part of), t - tag, s - spacer, o - o

        self.tag = head
        self.token_type = token_type

    def __repr__(self):
        return 'Token({}) {} {}'.format(self.value, self.tag, self.token_type)  # .encode('utf-8')


class CensorException(Exception):
    pass


class CensorBase:
    lang = 'ru'

    def __init__(self, do_compile=True):
        self.lang_lib = import_module('censure.lang.{}'.format(self.lang))

        if do_compile:
            # patterns will be pre-compiled, so we need to copy them
            def prep_var(v):
                return deepcopy(v)
        else:
            def prep_var(v):
                return v

        # language-related constants data loading and preparations
        self.bad_phrases = prep_var(self.lang_lib.constants.BAD_PHRASES)
        self.bad_semi_phrases = prep_var(self.lang_lib.constants.BAD_SEMI_PHRASES)
        self.excludes_data = prep_var(self.lang_lib.constants.EXCLUDES_DATA)
        self.excludes_core = prep_var(self.lang_lib.constants.EXCLUDES_CORE)
        self.foul_data = prep_var(self.lang_lib.constants.FOUL_DATA)
        self.foul_core = prep_var(self.lang_lib.constants.FOUL_CORE)

        self.do_compile = do_compile
        if do_compile:
            self._compile()  # will compile patterns

    def _compile(self):
        """
        For testing functional and finding regexp rules, under which the word falls,
        disable call for this function (in __init__) by specifying do_compile=False to __init__,
        then debug, fix bad rule and then use do_compile=True again
        """
        for attr in ('excludes_data', 'excludes_core',
                     'foul_data', 'foul_core', 'bad_semi_phrases', 'bad_phrases'):
            obj = getattr(self, attr)
            if isinstance(obj, dict):
                for (k, v) in obj.items():
                    # safe cause of from __future__ import unicode_literals
                    if isinstance(v, "".__class__):
                        obj[k] = re.compile(v)
                    else:
                        obj[k] = tuple((re.compile(v[i]) for i in range(0, len(v))))
                setattr(self, attr, obj)
            else:
                new_obj = []
                for i in range(0, len(obj)):
                    new_obj.append(re.compile(obj[i]))
                setattr(self, attr, new_obj)

    def check_line(self, line):
        line_info = {'is_good': True}
        words = self._split_line(line)
        # Checking each word in phrase line, if found any foul word,
        # we think that all phrase line is bad
        if words:
            for word in words:
                word_info = self.check_word(word)
                if not word_info['is_good']:
                    line_info.update({
                        'is_good': False,
                        'bad_word_info': word_info
                    })
                    break
        if line_info['is_good']:
            phrases_info = self.check_line_bad_phrases(line)
            if not phrases_info['is_good']:
                line_info.update(phrases_info)
        return line_info

    def check_line_bad_phrases(self, line):
        line_info = self._get_word_info(line)
        self._check_regexps(self.bad_phrases, line_info)
        line_info.pop('word')  # not the word but the line
        return line_info

    def _split_line(self, line):
        raise CensorException('Not implemented in CensorBase')

    def _prepare_word(self, word):
        if not self._is_pi_or_e_word(word):
            word = re.sub(patterns.PAT_PUNCT3, '', word)
        word = word.lower()
        for pat, rep in self.lang_lib.patterns.PATTERNS_REPLACEMENTS:
            word = re.sub(pat, rep, word)
        # replace similar symbols from another charsets with russian chars
        word = word.translate(self.lang_lib.constants.TRANS_TAB)
        # deduplicate chars
        word = self._remove_duplicates(word)
        return word

    @staticmethod
    def _get_word_info(word):
        return {
            'is_good': True, 'word': word,
            'accuse': [], 'excuse': []
        }

    def check_word(self, word, html=False):
        word = self._prepare_word(word)
        word_info = self._get_word_info(word)
        # Accusing word
        fl = word[:1]  # first_letter
        if fl in self.foul_data:
            self._check_regexps(self.foul_data[fl], word_info)
        if word_info['is_good']:  # still good, more accuse checks
            self._check_regexps(self.foul_core, word_info)
        if word_info['is_good']:  # still good, more accuse checks
            self._check_regexps(self.bad_semi_phrases, word_info)

        # Excusing word
        if not word_info['is_good']:
            self._check_regexps(self.excludes_core, word_info, accuse=False)  # excusing
        if not word_info['is_good'] and fl in self.excludes_data:
            self._check_regexps(self.excludes_data[fl], word_info, accuse=False)  # excusing
        return word_info

    @staticmethod
    def _is_pi_or_e_word(word):
        if '2.72' in word or '3.14' in word:
            return True
        return False

    def clean_line(self, line, beep=constants.BEEP):
        detected_bad_words = []
        detected_bad_phrases = []
        detected_pats = []
        bad_words_count = 0
        words = re.split(patterns.PAT_SPACE, line)
        for word in words:
            word_info = self.check_word(word)
            if not word_info['is_good']:
                bad_words_count += 1
                line = line.replace(word, beep, 1)
                detected_bad_words.append(word)
                detected_pats.append(word_info['accuse'][0])

        bad_phrases_count = 0
        line_info = self.check_line_bad_phrases(line)
        if not line_info['is_good']:
            for pat in line_info['accuse']:
                line2 = re.sub(pat, beep, line)
                if line2 != line:
                    bad_phrases_count += 1
                    detected_bad_phrases.append(pat)
                    detected_pats.append(pat)
                line = line2

        return line, bad_words_count, bad_phrases_count, detected_bad_words, detected_bad_phrases, detected_pats

    def clean_html_line(self, line, beep=constants.BEEP_HTML):
        bad_words_count = start = 0
        tokens = []
        for tag in re.finditer(patterns.PAT_HTML_TAG, line):  # iter over tags
            text = line[start:tag.start()]
            # find spaces in text
            spacers = re.finditer(patterns.PAT_SPACE, text)
            spacer_start = 0
            for spacer_tag in spacers:
                word = text[spacer_start:spacer_tag.start()]
                if word:
                    tokens.append(Token(token_type='w', value=word))
                tokens.append(Token(token_type='sp', value=spacer_tag.group()))
                spacer_start = spacer_tag.end()
            word = text[spacer_start:]
            if word:
                tokens.append(Token(token_type='w', value=word))
            start = tag.end()
            tokens.append(Token(value=tag.group()))
        word = line[start:]

        # LAST prep
        if word:
            tokens.append(Token(token_type='w', value=word))

        current_word = current_tagged_word = ''
        result = ''
        tagged_word_list = []

        def process_spacer(cw, ctw, twl, r, bwc, tok=None):
            if cw and not self.is_word_good(cw, html=True):
                # Here we must find pre and post badword tags to add in result,
                # ie <h1><b>BAD</b> -> <h1> must remain
                pre, post = _get_remained_tokens(twl)
                # bad word
                r += pre + beep + post
                bwc += 1

            else:
                # good word
                r += ctw
            twl = []
            cw = ctw = ''
            if tok:
                r += tok.value
            return cw, ctw, twl, r, bwc

        for token in tokens:
            if token.token_type in 'to tc ts':
                tagged_word_list.append(token)
                current_tagged_word += token.value
            elif token.token_type == 'w':
                tagged_word_list.append(token)
                current_tagged_word += token.value
                current_word += token.value
            else:
                # spacer here
                current_word, current_tagged_word, tagged_word_list, result, bad_words_count = \
                    process_spacer(current_word, current_tagged_word, tagged_word_list,
                                   result, bad_words_count, tok=token)
        if current_word:
            current_word, current_tagged_word, tagged_word_list, result, bad_words_count = \
                process_spacer(
                    current_word, current_tagged_word, tagged_word_list, result, bad_words_count,
                    tok=None)

        return result, bad_words_count

    def is_word_good(self, word, html=True):
        word_info = self.check_word(word, html=html)
        return word_info['is_good']

    def _get_rule(self, rule):
        if not self.do_compile:
            return rule
        else:
            return '{} {}'.format(
                rule,
                'If you want to see string-value of regexp, '
                'init with do_compile=False for debug'
            )

    @staticmethod
    def _remove_duplicates(word):
        buf = prev_char = ''
        count = 1  # can be <3
        for char in word:
            if char == prev_char:
                count += 1
                if count < 3:
                    buf += char
                # else skip this char, so AAA -> AA, BBBB -> BB, but OO -> OO, and so on
            else:
                count = 1
                buf += char
                prev_char = char
        return buf

    def _check_regexps(self, regexps, word_info, accuse=True, break_on_first=True):
        keys = None  # assuming list regexps here
        if isinstance(regexps, dict):
            keys = regexps.keys()
            regexps = regexps.values()

        for i, regexp in enumerate(regexps):
            if re.search(regexp, word_info['word']):
                rule = regexp
                if keys:  # dict rule set
                    rule = list(keys)[i]
                rule = self._get_rule(rule)
                if accuse:
                    word_info['is_good'] = False
                    word_info['accuse'].append(rule)
                else:
                    word_info['is_good'] = True
                    word_info['excuse'].append(rule)
                if break_on_first:
                    break


class CensorRu(CensorBase):
    lang = 'ru'

    def _split_line(self, line):
        buf, result = '', []
        line = re.sub(patterns.PAT_PUNCT2, ' ', re.sub(patterns.PAT_PUNCT1, '', line))
        for word in re.split(patterns.PAT_SPACE, line):
            if len(word) < 3 and not re.match(self.lang_lib.patterns.PAT_PREP, word):
                buf += word
            else:
                if buf:
                    result.append(buf)
                    buf = ''
                result.append(word)
        if buf:
            result.append(buf)
        return result


class CensorEn(CensorBase):
    lang = 'en'

    def _split_line(self, line):
        # have some differences from russian split_line
        buf, result = '', []
        line = re.sub(patterns.PAT_PUNCT2, ' ', re.sub(patterns.PAT_PUNCT1, '', line))
        for word in re.split(patterns.PAT_SPACE, line):
            if len(word) < 3:
                buf += word
            else:
                if buf:
                    result.append(buf)
                    buf = ''
                result.append(word)
        if buf:
            result.append(buf)
        return result


class Censor:
    supported_langs = {
        'ru': CensorRu,
        'en': CensorEn,
    }

    @staticmethod
    def get(lang='ru', do_compile=True, **kwargs):
        if lang not in Censor.supported_langs:
            raise CensorException(
                'Language {} is not yet in supported: {}. Please contribute '
                'to project to make it available'.format(
                    lang, sorted(Censor.supported_langs.keys())))
        return Censor.supported_langs[lang](do_compile=do_compile, **kwargs)
