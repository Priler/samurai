from aiogram import types
from aiogram.types import ChatMemberAdministrator, ChatMemberOwner, ContentType
from sympy.strategies.core import switch

from configurator import config
from dispatcher import dp
import localization
from time import time
import re
import utils
import lru_cache
import datetime
from aiogram.utils import exceptions

import random

import ormar
from models.member import Member
from models.spam import Spam

from ruspam import predict as ruspam_predict

from utils import Gender

# blacklist = open("blacklist.txt", mode="r").read().split(',')
# blacklist_regexp = re.compile(r'(?iu)\b((у|[нз]а|(хитро|не)?вз?[ыьъ]|с[ьъ]|(и|ра)[зс]ъ?|(о[тб]|под)[ьъ]?|(.\B)+?[оаеи])?-?([её]б(?!о[рй])|и[пб][ае][тц]).*?|(н[иеа]|[дп]о|ра[зс]|з?а|с(ме)?|о(т|дно)?|апч)?-?ху([яйиеёю]|ли(?!ган)).*?|(в[зы]|(три|два|четыре)жды|(н|сук)а)?-?бл(я(?!(х|ш[кн]|мб)[ауеыио]).*?|[еэ][дт]ь?)|(ра[сз]|[зн]а|[со]|вы?|п(р[ои]|од)|и[зс]ъ?|[ао]т)?п[иеё]зд.*?|(за)?п[ие]д[аое]?р((ас)?(и(ли)?[нщктл]ь?)?|(о(ч[еи])?)?к|юг)[ауеы]?|манд([ауеы]|ой|[ао]вошь?(е?к[ауе])?|юк(ов|[ауи])?)|муд([аио].*?|е?н([ьюия]|ей))|мля([тд]ь)?|лять|([нз]а|по)х|м[ао]л[ао]фь[яию])\b')

@dp.message_handler(chat_id=config.groups.main, content_types=["new_chat_members"])
async def on_user_join(message: types.Message):
    """
    Removes "user joined" message.

    :param message: Service message "User joined group
    """

    # remove invite message
    await message.delete()

    # restrict media for new users
    '''await message.bot.restrict_chat_member(chat_id=config.groups.main,
                                          user_id=message.from_user.id,
                                          permissions=types.ChatPermissions(True),
                                          until_date=int(time()) + int(config.groups.new_users_nomedia))'''

    await utils.write_log(message.bot, "Присоединился пользователь "+utils.user_mention(message.from_user), "➕ Новый участник")


@dp.message_handler(chat_id=config.groups.main, content_types=[types.ContentType.TEXT, types.ContentType.PHOTO, types.ContentType.DOCUMENT, types.ContentType.VIDEO])
@dp.edited_message_handler(chat_id=config.groups.main, content_types=[types.ContentType.TEXT, types.ContentType.PHOTO, types.ContentType.DOCUMENT, types.ContentType.VIDEO])
async def on_user_message(message: types.Message):
  """
  Process every user message.
  I.e. remove, if profanity is detected.
  Or remove, if spam is detected.
  Also log every user to database.

  :param message: Message in group
  """
  if message.is_automatic_forward:
      await message.reply(random.choice(["И так сойдет ...", "Бананчики 🍌", "Ну и кто теперь тут первый 😎", "Я не первый, не второй, я таких баню :3",
                                         "Заходи не бойся, выходи не плачь :3", "Автор ничего не постил уже 1 секунду, всё ясно скатился :3",
                                         "Самурай на страже порядке 🫡", "Постим живем :3", "Ладно", "Пока ты читаешь, я уже коммент оставил! Успевай 😈",
                                         "Кто на чем пишет? Я вот на Python :3", "Самурай на месте 😎", "Самурай без меча, как бот без токена :3",
                                         "Нулевой тутб :3", "Ох, умбаса ..", "Минутка полезной инфы. Сейчас принято считать, что 1МБ = 1000КБ. А 1МиБ = 1024 КиБ. Живи с этим.",
                                         "✌️ Здоровья и мира тебе, читающий это :3", f"Вышел ёжик из тумана ... вынул <tg-spoiler>{random.choice(['пайтон', 'раст', 'ЖС', 'джаву', 'катану', 'бананчики'])}</tg-spoiler> из кармана :3",
                                         "жаль, что далеко не все поймут в чем же дело))) действительно тонко))))) не так уж много и образованных в наше время, кто знает, почему это так интересно и необычно))))",
                                         "С великой силой приходит великая безответственность.", "Где-то однажды появился на свет\nС лаем и мяуканьем зверь, каких нет\nИ тут же сбежал, оставив вопрос,\nСобаче-кошачий малыш Котопес\nКотопес, котопес ...\nЕдинственный в мире малыш котопес.",
                                         "Его не признали в городе родном\nИ все его шпыняют и ночью и днем\nНе стоит огорчаться, не стоит робеть\nА лучше эту песенку вместе пропеть Котопес, котопес,\nЕдинственный в мире малыш котопес!",
                                         "Есть программисты, а есть ЖСеры пхпхпх", "100% понимания", "0% осуждения", "Бро как всегда на высоте.",

                                         # upd 2
                                         "Я всегда здесь первый, это уже традиция :3", "Когда-то и я был человеком... а теперь я лягух с катаной.", "Оп, Оп. Контент подъехал.",
                                         "Кажется, кто-то снова постит — пора комментить 😎", "Не пост, а произведение искусства 🎨",
                                         "Ниндзя-комментатор уже тут 🥷", "Лягух-комментатор уже тут 🐸", "Самурай-комментатор уже тут 🇯🇵",
                                         "Пост хорош, но комментарии — лучше.", "Я бы лайкнул, да не могу. Бот, всё-таки.",
                                         "Ноль токсичности, сто процентов ламповости 🕯", "Вот это ты, конечно, запостил… Уважение.",
                                         "Сначала идёт пост. Потом — комментарий. Потом — хаос. Но я слежу за порядком в чате 😎",
                                         "Ты постишь, я комментю. Стабильность.", "Я тут по расписанию. И пост — тоже.", "Пока ты думал, я уже комментнул пхпх.",
                                         "Где контент, Лебовски?", "Контент пришёл. Самурай доволен.",
                                         "Запушил пост, получил коммент — всё по CI/CD.", "На Python пишу, на Rust думаю, на JS страдаю.",
                                         "TypeError: пост слишком хорош", "git commit -m 'Топовый пост!'", "Код написан, чай налит, пост прочитан.",
                                         "В этом комментарии нет смысла. Но это нормально. Я же бот. Бип-буп ...", "Я пришёл из будущего. Пост всё ещё топ.",
                                         "По легенде, этот коммент приносит +10 к удаче 🍀", "Пост хороший. А ты ещё лучше, читатель ❤️",
                                         "Ты это лайкни, а я — понаблюдаю 👀", "Каждый пост заслуживает комментария. Даже этот.",
                                         "Пост увидел, коммент оставил, порядок навёл 🫡", "Где я? Кто я? А, точно — бот, читающий посты.",
                                         "Даже я, бот, прослезился ...", "Контент — 10/10, комменты — 11/10.", "Сам ты бот, пон :3",
                                         "На страже постов, как всегда 😎", "Картинка чёткая, постик годный, комментарии — шедевр.",
                                         "Сколько бы постов ни было — я везде первый. Бугага!", "Опять пост, опять шедевр. Так держать.",
                                         "Прекрасный день для прекрасного поста.", "Каждый день ты пишешь десятки комментариев, - почему бы не написать еще один?",
                                         "Зашёл, увидел, откомментил.", "Ты постишь, я комментирую. Симбиоз.", "В любой непонятной ситуации говори - да."
                                         ]))

      # await message.reply(random.choice(["Праздник к нам приходит 🎅", "Веселье приносит и вкус бодрящий\nПраздника вкус всегда настоящий 🎅", "Пачаны авик заберите с окна ...",
      #                                   "С наступающим, бро 🎅", "⛄️ Вот и наступила снежная пора\nВ этот праздник зимний каждый ждёт добра\nПоделитесь счастьем, нежностью, теплом\nЧтобы радость ваша согревала дом",
      #                                    "🎅 Новый год несёт любовь и счастье\nВсе мечты сбываются\nХауди Хо в дом приносит праздник\nПусть он продолжается",
      #                                    "🦌🦌🦌🦌🦌🦌🦌🦌🦌", "🎄 Попрошу у санты новую катану ... :3", "❄️ Зима уже близбко", "🎅 Санта Клавус существует. Change my mind :3",
      #                                    "🎅 Советую к просмотру фильм «Мальчик по имени Рождество».", "А ты уже посмотрел историю 💚 Гринча похитителя рождества?",
      #                                    "🎅 Духи рождества показали бы программистам весь их г@внокод ... и его последствия пхпхпх", "🧝 Эльфы на месте?",
      #                                    f"Вышел 🎅 Санта из тумана ... вынул <tg-spoiler>{random.choice(['пайтон', 'раст', 'ЖС', 'джаву', 'бананчики'])}</tg-spoiler> из кармана :3",
      #                                    "✌️ Здоровья и мира тебе, читающий это :3", "🌲🌲🌲🌲🌲\n🎄🎄🎄🎄🎄\n🌲В лесу родиласб йолочка :3\n🎄🎄🎄🎄🎄\n🌲🌲🌲🌲🌲"]))

      return # auto-forward channel messages should not be checked

  ### Retrieve member record from DB
  member = await lru_cache.retrieve_or_create_member(message.from_user.id)

  # Retrieve tg member object
  tg_member = await lru_cache.retrieve_tgmember(message.bot, message.chat.id, message.from_user.id)

  # Define message text
  msg_text = None

  if message.content_type == types.ContentType.TEXT:
      msg_text = message.text
  elif message.content_type in [types.ContentType.PHOTO, types.ContentType.DOCUMENT, types.ContentType.VIDEO]:
      msg_text = message.caption

  # Quit, if no message to check
  if msg_text is None:
      return

  ###   CHECK FOR PROFANITY & SPAM
  _del = False
  _word = None

  _del, _word = utils.check_for_profanity_all(msg_text)

  # process
  if _del:
    # PROFANITY DETECTED
    # if not (tg_member.is_chat_admin() and tg_member.can_restrict_members):
    if not tg_member.is_chat_admin():
        await message.delete()

        # increase member violations count
        member.violations_count_profanity += 1
        member.reputation_points -= 20 # every profanity message removes some reputation points from user
        await member.update()

    log_msg = msg_text
    if _word:
      log_msg = log_msg.replace(_word, '<u><b>'+_word+'</b></u>')
    log_msg += "\n\n<i>Автор:</i> "+utils.user_mention(message.from_user)

    await utils.write_log(message.bot, log_msg, "🤬 Антимат")
  else:
    ### NO PROFANITY, GO CHECK FOR SPAM
    if (member.messages_count < int(config.spam.member_messages_threshold) or member.reputation_points < int(config.spam.member_reputation_threshold)) and ruspam_predict(msg_text):
        # SPAM DETECTED
        # if not (tg_member.is_chat_admin() and tg_member.can_restrict_members):
        if not tg_member.is_chat_admin():
            await message.delete()

            # increase member violations count
            member.violations_count_spam += 1
            member.reputation_points -= 5  # every spam message removes some reputation points from user
            await member.update()

        # TEMPORARY TURN OFF SPAM DB LOGGING etc
        # log_msg = msg_text
        # log_msg += "\n\n<i>Автор:</i> " + utils.user_mention(message.from_user)
        #
        # # Create DB record on spam message
        # spam_rec = await Spam.objects.create(message=msg_text, is_spam=True, user_id=message.from_user.id, chat_id=int(config.groups.main)) # assume is spam by default
        #
        # # Generate keyboard with some actions for detected spam
        # spam_keyboard = types.InlineKeyboardMarkup()
        #
        # # is spam + block user
        # spam_keyboard.add(types.InlineKeyboardButton(
        #     text="❌ Это спам + заблокировать пользователя",
        #     callback_data=f"spam_ban_{spam_rec.id}_{message.from_user.id}")
        # )
        #
        # # not a spam
        # spam_keyboard.add(types.InlineKeyboardButton(
        #     text="❎ Это НЕ спам",
        #     callback_data=f"spam_invert_{spam_rec.id}_{member.id}")
        # )
        #
        # # test msg, remove from db
        # spam_keyboard.add(types.InlineKeyboardButton(
        #     text="Убрать из БД, это тест",
        #     callback_data=f"spam_test_{spam_rec.id}_{member.id}")
        # )
        #
        # # send message with a keyboard to log channel
        # await message.bot.send_message(
        #     config.groups.logs,
        #     utils.generate_log_message(log_msg, "❌ АнтиСПАМ"),
        #     reply_markup=spam_keyboard)
    else:
        # only if message doesn't contain any violations
        member.messages_count += 1 # increase members messages count
        member.reputation_points += 1 # increase members reputation points
        await member.update()


@dp.message_handler(is_owner = True, chat_id=config.groups.main, commands=["spam"], commands_prefix="!")
async def on_spam(message: types.Message):
    if not message.reply_to_message:
        await message.reply("Чего ты от меня хочешь :3")
        return

    ### Retrieve member record from DB
    member = await lru_cache.retrieve_or_create_member(message.reply_to_message.from_user.id)

    # Define message text
    msg_text = None
    if message.reply_to_message.content_type == types.ContentType.TEXT:
        msg_text = message.reply_to_message.text
    elif message.reply_to_message.content_type in [types.ContentType.PHOTO, types.ContentType.DOCUMENT, types.ContentType.VIDEO]:
        msg_text = message.reply_to_message.caption

    # Quit, if no message to check
    if msg_text is None:
        await message.reply("Нет текста - нет спама :3")
        return

    try:
        log_msg = msg_text
        log_msg += "\n\n<i>Автор:</i> " + utils.user_mention(message.reply_to_message.from_user)

        # Create DB record on spam message
        spam_rec = await Spam.objects.create(message=msg_text, is_spam=True, user_id=message.reply_to_message.from_user.id, chat_id=int(config.groups.main)) # assume is spam by default

        # Generate keyboard with some actions for detected spam
        spam_keyboard = types.InlineKeyboardMarkup()

        # is spam + block user
        spam_keyboard.add(types.InlineKeyboardButton(
            text="❌ Это спам + заблокировать пользователя",
            callback_data=f"spam_ban_{spam_rec.id}_{message.reply_to_message.from_user.id}")
        )

        # not a spam
        spam_keyboard.add(types.InlineKeyboardButton(
            text="❎ Это НЕ спам",
            callback_data=f"spam_invert_{spam_rec.id}_{member.id}")
        )

        # test msg, remove from db
        spam_keyboard.add(types.InlineKeyboardButton(
            text="Убрать из БД, это тест",
            callback_data=f"spam_test_{spam_rec.id}_{member.id}")
        )

        # send message with a keyboard to log channel
        await message.bot.send_message(
            config.groups.logs,
            utils.generate_log_message(log_msg, "❌ АнтиСПАМ"),
            reply_markup=spam_keyboard)

        # remove marked message from chat afterwards
        if not member.is_chat_admin():
            await message.reply_to_message.delete()

        await message.reply(f"🫡 Сообщение помечено как спам.</i>")
    except ValueError:
        await message.reply("O_o Мда")


@dp.message_handler(chat_id=config.groups.main, content_types=["voice"])
async def on_user_voice(message: types.Message):
    if random.random() < 0.75: # 75% chance to react
        ### Retrieve member record from DB
        member = await lru_cache.retrieve_or_create_member(message.from_user)

        await message.reply(random.choice(["фу! ФУ Я СКАЗАЛ, НЕЛЬЗЯ. БРОСЬ КАКУ. ПИШИ ТЕКСТОМ.", "Давай без резких движений! Положи телефон на пол ... и больше не записывай ГСки :3",
                                           "ГСки - бич современного общества. Делай выводы, макарошка :3", "А вот в моё время люди писали текстом ...",
                                           "ТЫ ПРИШЕЛ В ЭТОТ ЧАТ! Но ты пришел без уважения ...", "Сэр, вынужден сообщить вам, что общаться ГСками это признак отсутствия интеллекта.",
                                           "ГСки бож ... выйди с чата, не позорься.", "Фу! ФУ Я СКАЗАЛ! Пиши текстом."]))

        member.reputation_points -= 10 # every voice message removes some reputation points
        await member.update()


media_content_types = [
    ContentType.PHOTO,
    ContentType.VIDEO,
    ContentType.AUDIO,
    ContentType.DOCUMENT,
    ContentType.VOICE,
    ContentType.VIDEO_NOTE,
    ContentType.ANIMATION
]
@dp.message_handler(chat_id=config.groups.main, content_types=media_content_types)
async def on_user_media(message: types.Message):
    ### Retrieve member
    member = await lru_cache.retrieve_or_create_member(message.from_user.id)
    tg_member = await lru_cache.retrieve_tgmember(message.bot, message.chat.id, message.from_user.id)

    # User is not allowed to post media type messages, until he reaches required reputation points
    # exceptions: admins
    if not tg_member.is_chat_admin() and member.reputation_points < int(config.spam.allow_media_threshold):
        await message.delete()

@dp.message_handler(is_admin=False, chat_id=config.groups.main, content_types=[types.ContentType.TEXT, types.ContentType.PHOTO, types.ContentType.DOCUMENT, types.ContentType.VIDEO])
async def on_user_message_delete_woman(message: types.Message):
    if not(message.reply_to_message and message.reply_to_message.forward_from_chat and message.reply_to_message.forward_from_chat.id == config.groups.linked_channel):
        return

    ### Retrieve member
    member = await lru_cache.retrieve_or_create_member(message.from_user.id)
    tg_member = await lru_cache.retrieve_tgmember(message.bot, message.chat.id, message.from_user.id)

    # Try detect member gender
    member__gender = lru_cache.detect_gender(tg_member.user.first_name)

    if member__gender == Gender.FEMALE:
        # RECOGNIZED FEMALE
        # Women accounts is not allowed to post messages, until they reach required reputation points
        # exceptions: admins
        if not tg_member.is_chat_admin() and member.reputation_points < int(config.spam.allow_first_comments_threshold__woman):
            await message.delete()
            await utils.write_log(message.bot, f"Удалено сообщение: {message.text}\n\n<i>Автор:</i> {utils.user_mention(message.from_user)}", "🤖 Антивумен")
    else:
        # OTHER GENDER (or unknown/ambiguous)
        # remove any messages within 20 seconds after message posted
        # exceptions: admins, users with high enough reputation points
        if not tg_member.is_chat_admin() and member.reputation_points < int(config.spam.allow_first_comments_threshold) and (message.date - message.reply_to_message.forward_date).seconds <= int(config.spam.remove_first_comments_interval):
            try:
                await message.delete()
                await utils.write_log(message.bot, f"Удалено сообщение: {message.text}\n\n<i>Автор:</i> {utils.user_mention(message.from_user)}", "🤖 Антибот")
            except exceptions.MessageCantBeDeleted:
                pass


@dp.message_handler(chat_id=config.groups.main, commands="бу", commands_prefix="!/")
async def on_bu(message: types.Message):
  await message.reply(random.choice(["Бугага!", "Не пугай так!", "Боже ..", "Не мешай мне делать сложные компьютерные вычисления :3", "Хватит!",
                                     "Ладно ...", "Бл я аж вздрогнул ...", "Та за шо :3", "Страшна вырубай",
                                     "Не смешно :3", "Так и сердешный приступ можно словить!", "Сам ты б/у пон",
                                     "Я чуть не крашнулся от страха!", "Ты чево творишь ...", "Пугать ботов? Вот это смелость!",
                                     "АААААА! Ладно, шучу.", "Ты меня выключить хочешь??", "Я щас админов позову!",
                                     "Не делай так больше, ладно?", "Пфф .. нашел чем пугать.", "Пойду перезапущусь от страха.",
                                     "Шутки такие себе, если честно...", "БУквально испугался :3", "Ой всё ...", "Ну хоть предупреждай, нечестно же!",
                                     "ОМГ 😤", "Страшно, аж проц вспотел.", "Бу! А теперь ты испугайся :3", "Ладно, я испугался, но я записал это в лог.",
                                     "И что дальше?", "Мда ..", "Там где ты пугать учился, я там преподавал.", "🤖 Бип буп, буп бип."]))


# @dp.message_handler(chat_id=config.groups.main, commands=["конфеты", "sweets", "сладкое", "хэлоуин", "сладости"], commands_prefix="!/")
# async def on_sweets(message: types.Message):
#     ### Retrieve member record from DB
#     try:
#         # retrieve existing record
#         member = await Member.objects.get(user_id=message.from_user.id)
#     except ormar.NoMatch:
#         return
#
#     if random.random() < 0.05:  # 5% chance to get golden ticket
#         await message.reply("Поздравляю, в твоей шоколадке оказался <u>золотой билет</u> 🎫")
#         member.halloween_golden_tickets += 1
#         await member.update()
#     else:
#         if random.random() < 0.25: # 25% to get sweets
#             sweets_random = random.randrange(1, 100)
#             await message.reply(f"На тебе 🍬 <i>({sweets_random}шт.)</i>")
#             member.halloween_sweets += sweets_random
#             await member.update()
#         else:
#             if random.random() < 0.5: # 50% to get anything sweet
#                 await message.reply(random.choice(["Держи шоколадку 🍫", "Печеньку, сэр 🍪", "Вотб тебе пирог 🥧", "Вотб 🍭"]))
#                 member.halloween_sweets += 1
#                 await member.update()
#
#             else:
#                 if random.random() < 0.01: # 1% chance to get a pumpkin
#                     await message.reply("🎃 Вотб тебе тыква!")
#                     member.halloween_sweets += 100 # 1 pumpkin = 100 sweets
#                     await member.update()
#
#                 else:
#                     # no sweets this time :(
#                     await message.reply(
#                         random.choice(["Хватит с тебя, сладкоежка :3", "Гадости тебе, а не сладости пон :3\n<i>пхпхпп</i>",
#                                        "Сладкое вредно для зубов!", "Хватит жрать сладости пон :3",
#                                        "Будешь много кушатб сладостей, код не будет компилиться пхпхпх :3"]))

@dp.message_handler(chat_id=config.groups.main, commands=["me", "я", "info", "инфо", "lvl", "лвл", "whoami", "neofetch"], commands_prefix="!/")
async def on_me(message: types.Message):
    if message.reply_to_message and not message.reply_to_message.is_automatic_forward:
        user_id = message.reply_to_message.from_user.id
    else:
        user_id = message.from_user.id

    ### Retrieve member
    member = await lru_cache.retrieve_or_create_member(user_id)
    tg_member = await lru_cache.retrieve_tgmember(message.bot, message.chat.id, user_id)

    ### Check member name for profanity and censure, if required
    tg_member__full_name: str = tg_member.user.full_name.strip()
    _del = False
    _word = None
    _del, _word = utils.check_for_profanity_all(tg_member__full_name)

    if _del:
        tg_member__full_name = tg_member__full_name.replace(_word, '#'*len(_word))

    # Try detect member gender
    member__gender = lru_cache.detect_gender(tg_member.user.first_name)

    member_level = None
    if isinstance(tg_member, (ChatMemberAdministrator, ChatMemberOwner)) and tg_member.is_chat_creator():
        # owner
        member_level = "👑 Король"
        member_rep = "⭐️⭐️⭐️⭐️⭐️ Пять звёзд розыска"
        member_avatar = "✖️"
    elif isinstance(tg_member, (ChatMemberAdministrator, ChatMemberOwner)) and tg_member.can_restrict_members:
        # admin (actual)
        # member_level = random.choice(["🎃 Главная тыковка чата", "🎃 Безголовый всадник", "🎃 Повелитель ночи", "🎃 Тыквенный властелин"])
        member_level = random.choice(["Полицейский", "S.W.A.T.", "Агент ФБР", "Мститель", "Модератор", "Длань правосудия"])
        member_rep = "🛡 "
        member_avatar = random.choice(['👮','👮‍♂️','👮‍♀️','🚔','⚖️','🤖','😼','⚔️'])
    else:
        member_rep = ""

        if member.messages_count < 100:
            member_level = "🥷 Ноунейм"
        elif 100 <= member.messages_count < 500:
            member_level = "🌚 Новичок"
        elif 500 <= member.messages_count < 1000:
            member_level = "😎 Опытный"
        elif 1000 <= member.messages_count < 2000:
            member_level = "🤵 Профессионал"
        elif 2000 <= member.messages_count < 3000:
            member_level = "😈 Ветеран"
        elif 3000 <= member.messages_count < 5000:
            member_level = "⭐️ Мастер"
        else:
            member_level = "🌟 Легенда"

        if member__gender == Gender.FEMALE:
            member_avatar = random.choice(['👩‍🦰', '👩', '👱‍♀️', '👧', '👩‍🦱', '👩‍🦱', '🤵‍♀️', '👩‍🦳'])
        elif member__gender == Gender.MALE:
            member_avatar = random.choice(['👨‍🦳', '🧔', '🧑', '👨', '🧔‍♂️', '🧑‍🦰', '🧑‍🦱', '👨‍🦰', '👦', '🤵‍♂️'])
        else:
            member_avatar = random.choice(['🤖', '😼', '👻', '😺'])

        # if member.messages_count < 100:
        #     member_level = random.choice(["🧛 Неизвестный вампир", "🎃 Неизвестная тыква", "🐺 Безымянный оборотень"])
        # elif 100 <= member.messages_count < 500:
        #     member_level = "🌚 Восходящая луна"
        # elif 500 <= member.messages_count < 1000:
        #     member_level = "🎃 Тыковка"
        # elif 1000 <= member.messages_count < 2000:
        #     member_level = "👻 Ветеран искусства запугивания"
        # else:
        #     member_level = "⭐️🎃 Тыквенный мастер"

        # if member.reputation_points < -2000:
        #     member_rep = "⭐️⭐️⭐️⭐️⭐️ Пять звёзд розыска"
        # elif -2000 <= member.reputation_points < -1000:
        #     member_rep = "☠️ Особо опасный"
        # elif -1000 <= member.reputation_points < -500:
        #     member_rep = "💀 Тёмная личность"
        # elif -500 <= member.reputation_points < 0:
        #     member_rep = "👿 Плохая печенька"
        # elif 0 <= member.reputation_points < 100:
        #     member_rep = "😐 Нейтральный"
        # elif 100 <= member.reputation_points < 500:
        #     member_rep = "🙂 Хорошая печенька"
        # elif 500 <= member.reputation_points < 1000:
        #     member_rep = "😎 Звезда чата"
        # else:
        #     member_rep = "😇 Добрейший добряк"

    member_rep_label = ""
    if not tg_member.is_chat_creator():
        if member.reputation_points < -2000:
            member_rep_label = "⭐️⭐️⭐️⭐️⭐️ пять звёзд розыска"
        elif -2000 <= member.reputation_points < -1000:
            member_rep_label = "особо опасный"
        elif -1000 <= member.reputation_points < -500:
            member_rep_label = "тёмная личность"
        elif -500 <= member.reputation_points < 0:
            member_rep_label = "нарушитель"
        elif 0 <= member.reputation_points < 100:
            member_rep_label = "нейтральный"
        elif 100 <= member.reputation_points < 500:
            member_rep_label = "хороший"
        elif 500 <= member.reputation_points < 1000:
            member_rep_label = "очень хороший"
        else:
            member_rep_label = "великодушный"

    answer = f"{member_avatar} <b>{tg_member__full_name}</b>"
    # answer += f"\n\n<b>Репутация: </b>{member_level} <i>(<tg-spoiler>{member.messages_count}</tg-spoiler>)</i>"
    # answer += f"\n<b>Репутация: </b>{member_level} <i> • 『{member_rep} (<tg-spoiler>{member.reputation_points}</tg-spoiler>)』</i>"
    answer += f"\n<b>Репутация: </b>{member_level} <i> 『{member_rep}{member_rep_label} (<tg-spoiler>{member.reputation_points}</tg-spoiler>)』</i>"

    await message.reply(answer)


@dp.message_handler(is_owner = True, chat_id=config.groups.main, commands=["setlvl"], commands_prefix="!")
async def on_setlvl(message: types.Message):
    if not message.reply_to_message:
        await message.reply("Чего ты от меня хочешь :3")
        return

    ### Retrieve member record from DB
    member = await lru_cache.retrieve_or_create_member(message.reply_to_message.from_user.id)

    try:
        member.messages_count = abs(int(utils.remove_prefix(message.text, "!setlvl")))
        member.reputation_points += abs(int(utils.remove_prefix(message.text, "!setlvl")))

        if member.messages_count > 100000:
            await message.reply("Что куришь, другалёк? :3")
        else:
            await member.update()
            await message.reply("Ладно :3")
    except ValueError:
        await message.reply("O_o Мда")


@dp.message_handler(is_owner = True, chat_id=config.groups.main, commands=["reward"], commands_prefix="!")
async def on_reward(message: types.Message):
    if not message.reply_to_message:
        await message.reply("Чего ты от меня хочешь :3")
        return

    points = abs(int(utils.remove_prefix(message.text, "!reward")))

    ### Retrieve member record from DB
    member = await lru_cache.retrieve_or_create_member(message.reply_to_message.from_user.id)

    try:
        member.reputation_points += points

        if points > 100_000:
            await message.reply("Нетб :3")
        else:
            await member.update()
            # await message.reply(f"🎃 <b>Слушаюсь, повелитель!</b>\nУчастник чата благословлён вашей милостью, ему начислено <i><b>{points} очков репутации.</b></i>")
            await message.reply(f"➕ Участник чата получает <i><b>{points}</b> очков репутации.</i>")
    except ValueError:
        await message.reply("O_o Мда")


@dp.message_handler(is_owner = True, chat_id=config.groups.main, commands=["rreset"], commands_prefix="!")
async def on_rep_reset(message: types.Message):
    if not message.reply_to_message:
        await message.reply("Чего ты от меня хочешь :3")
        return

    ### Retrieve member record from DB
    member = await lru_cache.retrieve_or_create_member(message.reply_to_message.from_user.id)

    try:
        member.reputation_points = member.messages_count

        await member.update()
        await message.reply(f"☯ Уровень репутации участника <i><b>сброшен</b>.</i>")
    except ValueError:
        await message.reply("O_o Мда")


@dp.message_handler(is_owner = True, chat_id=config.groups.main, commands=["punish"], commands_prefix="!")
async def on_punish(message: types.Message):
    if not message.reply_to_message:
        await message.reply("Чего ты от меня хочешь :3")
        return

    points = abs(int(utils.remove_prefix(message.text, "!punish")))

    ### Retrieve member record from DB
    member = await lru_cache.retrieve_or_create_member(message.reply_to_message.from_user.id)

    try:
        member.reputation_points -= points

        if points > 100_000:
            await message.reply("Нетб :3")
        else:
            await member.update()
            await message.reply(f"➖ Участник чата теряет <i><b>{points}</b> очков репутации.</i>")
    except ValueError:
        await message.reply("O_o Мда")

'''async def on_user_message(message: types.Message):
  """
  Removes messages, if they contain black listed words.

  :param message: Message in group
  """
  _del = False
  _word = None

  for w in blacklist:
    if w in message.text:
      _del = True
      _word = w
      break

  _result = blacklist_regexp.search(message.text)

  if _result:
    _word = _result.group(0)
    _del = True

  if _del:
    await message.delete()

    log_msg = message.text
    if _word:
      log_msg = log_msg.replace(_word, '<u><b>'+_word+'</b></u>')
    log_msg += "\n\n<i>Автор:</i> "+message.from_user.full_name+" ("+message.from_user.mention+")"

    await utils.write_log(message.bot, log_msg, "Антимат")'''

'''@dp.message_handler(chat_id=config.groups.main)
async def do_ro_filter_messages(message: types.Message):
  user = await message.bot.get_chat_member(config.groups.main, message.from_user.id)

  # @TODO: small optimization can be done, by muting not muted members for a minute (or so)
  # but in this case there may be problems with restrictions (after restriction period ended, telegram returns
  # back the default chat restrictions, but not users previous restrictions)
  if builtins.RO and not user.is_chat_admin():
    await message.bot.delete_message(config.groups.main, message.message_id)'''
