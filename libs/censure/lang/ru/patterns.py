# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import re


PAT_EUML = re.compile('&[Ee][Uu][Mm][Ll];')   # e
PAT_IUML = re.compile('&[Uu][Uu][Mm][Ll];')   # и
PAT_AUML = re.compile('&[Aa][Uu][Mm][Ll];')   # а
PAT_OUML = re.compile('&[Oo][Uu][Mm][Ll];')   # о
PAT_YUML = re.compile('&[Yy][Uu][Mm][Ll];')   # у

PAT_CENT = re.compile('&[Cc][Ee][Nn][Tt];')   # c
PAT_CODE203 = re.compile('&#203;')            # e
PAT_CODE162 = re.compile('&#162;')            # c
PAT_CODE120 = re.compile('&#120;')            # х
PAT_CODE121 = re.compile('&#121;')            # у

PAT_AS_I = re.compile(r'\|\\\|')                # И
PAT_AS_L = re.compile(r'/\\')                 # Л

PAT_AS_X1 = re.compile(r'><')                 # Х
PAT_AS_X2 = re.compile(r'><')                 # Х
PAT_AS_X3 = re.compile('\)\(')                # Х
PAT_AS_X4 = re.compile('}{')                  # Х

PAT_AS_J1 = re.compile('>\|<')                # Ж
PAT_AS_J2 = re.compile('}\|{')                # Ж

PAT_AS_Y1 = re.compile('`/')                  # Y
PAT_AS_Y2 = re.compile('\-/')                 # Y
PAT_AS_Y3 = re.compile('`\-/')                # Y

PAT_AS_YY1 = re.compile('b\|')                # ы
PAT_AS_YY2 = re.compile('bI')                 # ы
PAT_AS_YY3 = re.compile('bl')                 # ы


PAT_PI = re.compile('3[\.,]14[\d]*')
PAT_E = re.compile('2[\.,]72[\d]*')
PAT_PREP = re.compile('(а[х]?)|(в)|([вмт]ы)|(д[ао])|(же)|(за)')


PATTERNS_REPLACEMENTS = (
    (PAT_EUML, 'е'),        # euml
    (PAT_IUML, 'и'),        # iuml
    (PAT_AUML, 'а'),        # auml
    (PAT_OUML, 'о'),        # ouml
    (PAT_YUML, 'у'),        # yuml

    (PAT_CODE203, 'е'),

    (PAT_CENT, 'с'),        # cent
    (PAT_CODE162, 'с'),

    (PAT_AS_I, 'и'),         # as И
    (PAT_AS_L, 'л'),         # as Л

    (PAT_AS_X1, 'х'),         # as Х
    (PAT_AS_X2, 'х'),         # as Х
    (PAT_AS_X3, 'х'),         # as Х
    (PAT_AS_X4, 'х'),         # as Х

    (PAT_AS_J1, 'ж'),         # as ж
    (PAT_AS_J2, 'ж'),         # as ж

    (PAT_AS_Y1, 'y'),         # as y
    (PAT_AS_Y2, 'y'),         # as y
    (PAT_AS_Y3, 'y'),         # as y

    (PAT_AS_YY1, 'ы'),         # as ы
    (PAT_AS_YY2, 'ы'),         # as ы
    (PAT_AS_YY3, 'ы'),         # as ы

    (PAT_CODE120, 'х'),
    (PAT_CODE121, 'у'),
    (PAT_PI, 'пи'),         # 3.14...
    (PAT_E, 'е'),           # 2.72...
)
