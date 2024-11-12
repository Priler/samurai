# -*- coding: utf-8 -*-
# based on the words from http://www.noswearing.com/dictionary/

from __future__ import unicode_literals


EXCLUDES_DATA = {

}


EXCLUDES_CORE = {

}

#    'cum': '^cum(($)|(bubble)|(dumpster)|()|()',
FOUL_DATA = {
    'a': [
        '^anus',
        '^axwound',
    ],
    'b': [
        '^bampot',
        '^bastar[dt]',
        '^beaner',
        '^blow(job)$',
        '^bollo(x|cks)',
        '^boner$',
    ],
    'c': [
        '^cameltoe$',
        '^carpetmuncher',
        '^chesticle',
        '^chin[ck]$',
        '^choad$',
        '^chode$',
        '^cooch(ie|y)$',
        '^coon$',
        '^cooter$',
    ],
    'd': [
        '^damn$',
        '^d[iy]ke$',
        '^dildo',
        '^dipshit',
        '^doochbag',
        '^dookie',
        '^douche($|(fag)|(bag)|(waffle))',
    ],
    'f': [
        '^fellatio',
        '^feltch',
        '^flamer',
        '^fudgepacker',
    ],
    'g': [
        '^godd[au]mn(it)*',
        '^gooch',
        '^gook',
    ],
    'h': [
        '^handjob',
        '^hard(on)*',
        '^homodumbshit',
        '^humping',
    ],
    'j': [
        '^jagoff',
        '^jizz',

    ],
    'k': [
        '^koo[t]*ch',
        '^kunt',
    ],
    'l': [
        'lameass',
        'lardass',
        '^lesb(ian|o)',
        '^lezzie',
    ],
    'm': [
        '^mcfagget',
        '^minge',
        '^muff(diver)*',
        '^munging',
        '^m[uo][thd]{1,3}erf[ou][ck]{1,}(er)?'
    ],
    'n': [
        '^nutsack'
    ],
    'p': [
        '^panooch',
        '^polesmoker',
        '^punta',
        '^puto',
    ],

    'r': [
        '^renob',
        '^rimjob',
    ],
    's': [
        '^schlong',
        '^scrote',
        '^skank',
        '^skeet',
        '^smeg',
        '^snatch',
        'splooge',
    ],
    't': [
        '^tard',
        'testicle',
        # '^tit(ty)*$',
    ],

}

FOUL_CORE = {
    # a
    'arse': '^arse((hole)|$)',
    'ass': '^ass((butt)|(idiot)|(hat)|(jabber)|(pirate)|(bag)|(banger)|'
           '(bandit)|(bite)|(clown)|(cock)|(cracker)|(es)|(face)|(goblin)|'
           '(hat)|(head)|(hole)|(hopper)|(jacker)|(lick)|(licker)|(monkey)|'
           '(munch)|(nigger)|(hit)|(sucker)|(ucker)|(wad)|(wipe)|$)',
    'bitch': '^bitch',
    'bullshit': '^bullshit$',
    'butt': '^butt((plug)|(pirate)|($))',


    'clit': '^clit(($)|(or)|(face))',
    'cum': '^cum(($)|(bubble)|(dumpster)|(guzzler)|(jockey)|(slut)|(tart))',
    'cunni': '^cunni(($)|(e)|(lingus))',
    'cock': '^cock($|(ass)|(bite)|(burger)|(face)|(head)|(jockey)|(knoker)|'
            '(master)|(mong(ler|ruel))|(monkey)|(muncher)|(nose)|'
            '(nugget)|(shit)|(smith)|(smoke)|(sniffer)|(sucker)|(waffle))',

    'cunt': '^cunt(($)|(ass)|(face)|(hole)|(licker)|(rag)|(slut))$',

    'dick': '^dick(([s]*$)|(bag)|(beaters)|(face)|(head)|(hole)|'
            '(juice)|(milk)|(monger)|(slap)|(suck(er|in))|'
            '(tickler)|(wad)|(weasel)|(weed)|(wod))',
    'dumb': 'dum(b)*($|(ass)|(shit))',

    'fag': 'fag($|(bag)|(g[io]t)|(tard)|(ass))',

    'gay': 'gay((ass)|(bob)|(do)|(lord)|(tard)|(wad))',

    'jackass': 'jackass',
    'jerk': 'jerk((o[f]+)|(ass))',

    'mothafucka': 'm[oa](th|z)afuck(a|in[g]*|er)',
    'penis': '^penis(banger|puffer)',
    'pecker': 'pecker(head)*',
    'piss': '^piss((ed)*(off)*|flaps)',
    'poon': '^p(oo|u)n(an(n)*[iy]|tang|$)',
    'prick': '^prick$',
    'pussy': '^puss((y)*(lick)*|ies)',

    'quee': 'quee(f|r($|bait|hole))',
    'suck': '^suck(ass|$)',
    'shit': '^shit($|ass|bag|brains|breath|canned|cunt|dick|face|faced|head|hole|house|'
            'spitter|stain|(t)*(er|iest|ing|y))',
    'slut': '^slut($|bag)',
    'shiz': '^shiz(nit)*$',
    'twat': '^twat(lips|s|waffle|$)',
    'vjay': '^vjayjay',
    'wank': '^wank(job|$)',
    'whore': '^whore(bag|face|$)',
}


BAD_SEMI_PHRASES = (
    'suckmydick',
    'sickmyduck',
    'cameltoe',
)

BAD_PHRASES = (
    'camel(\s)*toe',
    'dick[\-\s]*sneeze',
    'blow[\-\s]*job',
    'jerk[\-\s]*off',
    'nut[\-\s]*sack'
)

TRANS_TAB = {}
