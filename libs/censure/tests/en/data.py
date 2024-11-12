# -*- coding: utf-8 -*-
from __future__ import unicode_literals

SIMPLE_OBSCENE_WORDS = (
    'shit',
    'motherfucker',
    'prick',
    'dildo',
    'bitch',
    'whore'
)

SIMPLE_OBSCENE_PHRASES = (
    'camel  toe',
    # 'dick sneeze', -> results in '[beep] sneeze' and not '[beep]' cause of word dick pattern
    'dick-sneeze',
    'blow job'
)

OBSCENE_HTML_LINES = (
    (
        '<b>б<i>sh</b>it<i> this bi<span>tch</i>',
        '[beep]<i> this [beep]</i>'
    ),
)
