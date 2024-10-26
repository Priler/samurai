import ormar
from aiogram import types
from aiogram.types import ChatMemberAdministrator, ChatMemberOwner
from sympy.strategies.core import switch

from configurator import config
from dispatcher import dp
import localization
from time import time
import re
import utils
import datetime
from aiogram.utils import exceptions

import random

from models.member import Member
from models.spam import Spam

from ruspam import predict as ruspam_predict

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
      await message.reply(random.choice(["Бананчики", "Ну и кто теперь тут первый 😎", "Я не первый, не второй, я таких баню :3",
                                         "Заходи не бойся, выходи не плачь :3", "Автор ничего не постил уже 1 секунду, всё ясно скатился :3",
                                         "Самурай на страже порядке 🫡", "Постим живем :3", "Ладно", "Пока ты читаешь, я уже коммент оставил! Успевай 😈",
                                         "Кто на чем пишет? Я вот на Python :3", "Самурай на месте 😎", "Самурай без меча, как бот без токена :3",
                                         "Нулевой тутб :3", "Ох, умбаса ..", "Минутка полезной инфы. Сейчас принято считать, что 1МБ = 1000КБ. А 1МиБ = 1024 КиБ. Живи с этим.",
                                         "✌️ Здоровья и мира тебе, читающий это :3", "Вышел ёжик из тумана ... вынул <tg-spoiler>пайтон</tg-spoiler> из кармана :3",
                                         "жаль, что далеко не все поймут в чем же дело))) действительно тонко))))) не так уж много и образованных в наше время, кто знает, почему это так интересно и необычно))))",
                                         "С великой силой приходит великая безответственность."]))
      return # auto-forward channel messages should not be checked

  ### Retrieve member record from DB
  try:
    # retrieve existing record
    member = await Member.objects.get(user_id=message.from_user.id)
  except ormar.NoMatch:
    # create new record
    member = await Member.objects.create(user_id=message.from_user.id, messages_count=1)

  # Retrieve tg member object
  tg_member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)

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
    if not (tg_member.is_chat_admin() and tg_member.can_restrict_members):
        await message.delete()

        # increase member violations count
        member.violations_count_profanity += 1
        member.reputation_points -= 10 # every profanity message removes some reputation points from user
        await member.update()

    log_msg = msg_text
    if _word:
      log_msg = log_msg.replace(_word, '<u><b>'+_word+'</b></u>')
    log_msg += "\n\n<i>Автор:</i> "+utils.user_mention(message.from_user)

    await utils.write_log(message.bot, log_msg, "🤬 Антимат")
  else:
    ### NO PROFANITY, GO CHECK FOR SPAM
    if member.messages_count < int(config.spam.member_messages_threshold) and ruspam_predict(msg_text):
        # SPAM DETECTED
        if not (tg_member.is_chat_admin() and tg_member.can_restrict_members):
            await message.delete()

            # increase member violations count
            member.violations_count_spam += 1
            await member.update()

        log_msg = msg_text
        log_msg += "\n\n<i>Автор:</i> " + utils.user_mention(message.from_user)

        # Create DB record on spam message
        spam_rec = await Spam.objects.create(message=msg_text, is_spam=True) # assume is spam by default

        # Generate keyboard with some actions for detected spam
        spam_keyboard = types.InlineKeyboardMarkup()

        # is spam + block user
        spam_keyboard.add(types.InlineKeyboardButton(
            text="❌ Это спам + заблокировать пользователя",
            callback_data=f"spam_ban_{message.from_user.id}")
        )

        # not a spam
        spam_keyboard.add(types.InlineKeyboardButton(
            text="❎ Это НЕ спам",
            callback_data=f"spam_invert_{spam_rec.id}")
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
    else:
        # increase members messages count (only if message doesn't contain any violations)
        member.messages_count += 1
        await member.update()

@dp.message_handler(chat_id=config.groups.main, content_types=["voice"])
async def on_user_voice(message: types.Message):
    if random.random() < 0.75: # 75% chance to react
        await message.reply(random.choice(["фу! ФУ Я СКАЗАЛ, НЕЛЬЗЯ. БРОСЬ КАКУ. ПИШИ ТЕКСТОМ.", "Давай без резких движений! Положи телефон на пол ... и больше не записывай ГСки :3",
                                           "ГСки - бич современного общества. Делай выводы, макарошка :3", "А вот в моё время люди писали текстом ...",
                                           "ТЫ ПРИШЕЛ В ЭТОТ ЧАТ! Но ты пришел без уважения ...", "Сэр, вынужден сообщить вам, что общаться ГСками это признак отсутствия интеллекта.",
                                           "ГСки бож ... выйди с чата, не позорься.", "Фу! ФУ Я СКАЗАЛ! Пиши текстом."]))


@dp.message_handler(is_admin=False, chat_id=config.groups.main, content_types=[types.ContentType.TEXT, types.ContentType.PHOTO, types.ContentType.DOCUMENT, types.ContentType.VIDEO])
async def on_user_message_delete_woman(message: types.Message):
    if message.reply_to_message and message.reply_to_message.forward_from_chat and message.reply_to_message.forward_from_chat.id == config.groups.linked_channel:
        if (message.date - message.reply_to_message.forward_date).seconds <= 20: #test
            try:
                await message.delete()
                await utils.write_log(message.bot, f"Удалено сообщение: {message.text}", "🤖 Антибот")
            except exceptions.MessageCantBeDeleted:
                pass


@dp.message_handler(chat_id=config.groups.main, commands="бу", commands_prefix="!/")
async def on_bu(message: types.Message):
  await message.reply(random.choice(["Бугага!", "Не пугай так!", "Боже ..", "Не мешай мне делать сложные компьютерные вычисления :3", "Хватит!", "Ладно ...", "Бл я аж вздрогнул ...", "Та за шо :3", "Страшна вырубай", "Не смешно :3", "Так и сердешный приступ можно словить!", "Сам ты б/у пон"]))

@dp.message_handler(chat_id=config.groups.main, commands=["конфеты", "sweets", "сладкое", "хэлоуин", "сладости"], commands_prefix="!/")
async def on_sweets(message: types.Message):
    if random.random() < 0.05:  # 5% chance to get golden ticket
        await message.reply("Поздравляю, в твоей шоколадке оказался <u>золотой билет</u> 🎫")
    else:
        await message.reply(random.choice(["Хватит с тебя, сладкоежка :3", "Гадости тебе, а не сладости пон :3\n<i>пхпхпп</i>", f"На тебе 🍬 <i>({random.randrange(1, 100)}шт.)</i>", "Держи шоколадку 🍫", "Печеньку, сэр 🍪", "Вотб тебе пирог 🥧", "Вотб 🍭", "Сладкое вредно для зубов!", "Хватит жрать сладости пон :3", "Будешь много кушатб сладостей, код не будет компилиться пхпхпх :3"]))

@dp.message_handler(chat_id=config.groups.main, commands=["me", "я", "info", "инфо", "lvl", "лвл"], commands_prefix="!/")
async def on_me(message: types.Message):
    if message.reply_to_message and not message.reply_to_message.is_automatic_forward:
        user_id = message.reply_to_message.from_user.id
    else:
        user_id = message.from_user.id

    ### Retrieve member record from DB
    try:
        # retrieve existing record
        member = await Member.objects.get(user_id=user_id)
    except ormar.NoMatch:
        return

    tg_member = await message.bot.get_chat_member(message.chat.id, user_id)

    member_level = None
    if isinstance(tg_member, (ChatMemberAdministrator, ChatMemberOwner)) and (tg_member.is_chat_creator() or tg_member.can_restrict_members):
        member_level = random.choice(["🎃 Главная тыковка чата", "🎃 Безголовый всадник", "🎃 Повелитель ночи", "🎃 Тыквенный властелин"])
        # member_rep = "🛡 Неприкосновенный"
    else:
        # if member.messages_count < 100:
        #     member_level = "🥷 Ноунейм"
        # elif 100 <= member.messages_count < 500:
        #     member_level = "🌚 Новичок"
        # elif 500 <= member.messages_count < 1000:
        #     member_level = "😎 Опытный"
        # elif 1000 <= member.messages_count < 2000:
        #     member_level = "😈 Ветеран"
        # else:
        #     member_level = "⭐️ Мастер"

        if member.messages_count < 100:
            member_level = random.choice(["🧛 Неизвестный вампир", "🎃 Неизвестная тыква", "🐺 Безымянный оборотень"])
        elif 100 <= member.messages_count < 500:
            member_level = "🌚 Восходящая луна"
        elif 500 <= member.messages_count < 1000:
            member_level = "🎃 Тыковка"
        elif 1000 <= member.messages_count < 2000:
            member_level = "👻 Ветеран искусства запугивания"
        else:
            member_level = "⭐️🎃 Тыквенный мастер"

    if member.reputation_points < -2000:
        member_rep = "⭐️⭐️⭐️⭐️⭐️ Пять звёзд розыска"
    elif -2000 <= member.reputation_points < -1000:
        member_rep = "☠️ Особо опасный"
    elif -1000 <= member.reputation_points < -500:
        member_rep = "💀 Тёмная личность"
    elif -500 <= member.reputation_points < 0:
        member_rep = "👿 Плохая печенька</i>"
    elif 0 <= member.reputation_points < 100:
        member_rep = "😐 Нейтральный"
    elif 100 <= member.reputation_points < 500:
        member_rep = "🙂 Хорошая печенька"
    elif 500 <= member.reputation_points < 1000:
        member_rep = "😎 Звезда чата"
    else:
        member_rep = "😇 Добрейший добряк"

    answer = f"{random.choice(['👩‍🦰','👨‍🦳','🧔','👩','👱‍♀️','🧑','👨','🧔‍♂️','🤖','😼','🧑‍🦰','🧑‍🦱','👨‍🦰','👦'])} <b>Участник чата:</b> {utils.user_mention(tg_member.user)}"
    answer += f"\n\n<i>{member_level}</i> <i>(<tg-spoiler>{member.messages_count}</tg-spoiler>)</i>"
    answer += f"\n<i>{member_rep}</i> <i>(<tg-spoiler>{member.reputation_points}</tg-spoiler>)</i>"

    await message.reply(answer)


@dp.message_handler(is_owner = True, chat_id=config.groups.main, commands=["setlvl"], commands_prefix="!")
async def on_setlvl(message: types.Message):
    if not message.reply_to_message:
        await message.reply("Чего ты от меня хочешь :3")
        return

    ### Retrieve member record from DB
    try:
        # retrieve existing record
        member = await Member.objects.get(user_id=message.reply_to_message.from_user.id)
    except ormar.NoMatch:
        return

    try:
        member.messages_count = abs(int(utils.remove_prefix(message.text, "!setlvl")))

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
    try:
        # retrieve existing record
        member = await Member.objects.get(user_id=message.reply_to_message.from_user.id)
    except ormar.NoMatch:
        return

    try:
        member.reputation_points += points

        if points > 100_000:
            await message.reply("Нетб :3")
        else:
            await member.update()
            await message.reply(f"🎃 <b>Слушаюсь, повелитель!</b>\nУчастник чата благословлён вашей милостью, ему начислено <i><b>{points} очков репутации.</b></i>")
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
