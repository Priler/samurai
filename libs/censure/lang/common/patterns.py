# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import re

PAT_HTML_TAG = re.compile('(<.*?>)|(&[\w]{2,6};)|(<![-]+)|([-]+>)')
# PAT_HTML_TAG_OR_SPACER = re.compile('(?P<tag><.*?>)|(?P<spacer>[\s]+)')
PAT_HTML_CSS = re.compile('[\w\s}{\.#;:\-\+]')
PAT_HTML_SPACE = re.compile('&nbsp;', re.IGNORECASE)

PAT_PUNCT1 = re.compile('[\"\-\+;\.,\*\?\(\)]+')
PAT_PUNCT2 = re.compile('[!:_]+')
PAT_PUNCT3 = re.compile('[\"\-\+;\.,\*\?\(\)!:_]+')

PAT_SPACE = re.compile('[\s]+')
