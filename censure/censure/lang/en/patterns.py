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


PATTERNS_REPLACEMENTS = (
    (PAT_EUML, 'e'),        # euml
    (PAT_IUML, 'u'),        # iuml
    (PAT_AUML, 'a'),        # auml
    (PAT_OUML, 'o'),        # ouml
    (PAT_YUML, 'y'),        # yuml

    (PAT_CODE120, 'x'),
    (PAT_CODE121, 'y'),
    (PAT_CODE203, 'e'),

    (PAT_CENT, 'c'),        # cent
    (PAT_CODE162, 'c'),
)
