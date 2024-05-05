from aiogram import types
from configurator import config
from dispatcher import dp
import localization
from time import time
import re
import utils
import datetime
from aiogram.utils import exceptions

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

    await utils.write_log(message.bot, "Присоединился пользователь "+utils.user_mention(message.from_user), "Новый участник")

@dp.message_handler(is_admin=False, chat_id=config.groups.main)
@dp.edited_message_handler(is_admin=False, chat_id=config.groups.main)
async def on_user_message_censor_filter(message: types.Message):
  """
  Removes messages, if they contain censored words.

  :param message: Message in group
  """
  _del = False
  _word = None

  _del, _word = utils.check_for_profanity_all(message.text)

  # process
  if _del:
    await message.delete()

    log_msg = message.text
    if _word:
      log_msg = log_msg.replace(_word, '<u><b>'+_word+'</b></u>')
    log_msg += "\n\n<i>Автор:</i> "+utils.user_mention(message.from_user)

    await utils.write_log(message.bot, log_msg, "Антимат")

@dp.message_handler(chat_id=config.groups.main, content_types=["voice"])
async def on_user_voice(message: types.Message):
  await message.reply(localization.get_string("voice_message_reaction"))

@dp.message_handler(is_admin=False, chat_id=config.groups.main)
async def on_user_message_delete_woman(message: types.Message):
    if message.reply_to_message and message.reply_to_message.forward_from_chat and message.reply_to_message.forward_from_chat.id == config.groups.linked_channel:
        if (message.date - message.reply_to_message.forward_date).seconds <= 20: #test
            try:
                await message.delete()
                await utils.write_log(message.bot, f"Удалено сообщение: {message.text}", "Антибот")
            except exceptions.MessageCantBeDeleted:
                pass

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
