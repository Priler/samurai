# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from censure.lang.common.constants import BEEP


SIMPLE_OBSCENE_WORDS = (
    'пидорги',
    'ебланаи',
    'хуй',
    'пизда',
    'блядва',
    'еблохуй'
)

E_OBSCENE_WORDS = (
    '2.72блан',
    '2.72баться',
    'п2.72здец',
    '2.72111блан',
    '2.72222баться',
    'п2.72333здец',
)

PI_OBSCENE_WORDS = (
    '3.14здец',
    '3.14дор',
    '3.14дорги',
    '3.14зда',
)

OBSCENE_HTML_LINES = (
    (
        ('<b>б<i>ля</b> пи<i>да&lt;ра</i>сы еба<span>нyты2.72</span> '
         'пи&gt;зд<a>a <p>д<o>лбое<i>бы</p>'),
        '<b>{beep}</b> {beep} {beep} {beep} <p>{beep}</p>'.format(beep=BEEP)
    ),
    (
        '<strong>апездал</strong>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;дилитант<br />',
        '<strong>{beep}</strong>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;дилитант<br />'.format(
            beep=BEEP)
    ),
    (
        ('<H1><img><eM>зл<b>а</B>е</em><strong>бучий</strong>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;'
         'нехороший,плохой<br />'),
        '<H1><img>{beep}&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;нехороший,плохой<br />'.format(
            beep=BEEP)
    )
)
