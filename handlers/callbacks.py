from time import time
from aiogram import types
from configurator import config
from dispatcher import dp
import localization

from contextlib import suppress
from aiogram.utils.exceptions import (MessageToEditNotFound, MessageCantBeEdited, MessageCantBeDeleted,
                                      MessageToDeleteNotFound, CantRestrictChatOwner)

from models.member import Member
from models.spam import Spam

@dp.callback_query_handler()
async def callback_handler(call: types.CallbackQuery):
    """
    Keyboard buttons handler

    :param call: Callback with action put into call.data field
    """

    ###
    ### REPORT callbacks
    ###
    if call.data.startswith("del_"):
        with suppress(MessageCantBeDeleted, MessageToDeleteNotFound):
            await call.message.bot.delete_message(config.groups.main, int(call.data.split("_")[1]))

        await call.message.bot.edit_message_text(chat_id=config.groups.reports,
                                                 message_id=call.message.message_id,
                                                 text=call.message.text + localization.get_string("action_deleted"))
        await call.answer(text="Done")

    elif call.data.startswith("delban_"):
        with suppress(MessageCantBeDeleted, MessageToDeleteNotFound):
            await call.message.bot.delete_message(config.groups.main, int(call.data.split("_")[1]))

        await call.message.bot.kick_chat_member(chat_id=config.groups.main, user_id=call.data.split("_")[2])
        await call.message.bot.edit_message_text(chat_id=config.groups.reports,
                                                 message_id=call.message.message_id,
                                                 text=call.message.text + localization.get_string(
                                                     "action_deleted_banned"))
        await call.answer(text="Done")

    elif call.data.startswith("mute_"):
        with suppress(MessageCantBeDeleted, MessageToDeleteNotFound):
            await call.message.bot.delete_message(config.groups.main, int(call.data.split("_")[1]))

        await call.message.bot.restrict_chat_member(chat_id=config.groups.main, user_id=call.data.split("_")[2],
                                                    permissions=types.ChatPermissions(),
                                                    until_date=int(time()) + (3600 * 24))  # 24 hours from now
        await call.message.bot.edit_message_text(chat_id=config.groups.reports,
                                                 message_id=call.message.message_id,
                                                 text=call.message.text + localization.get_string(
                                                     "action_deleted_readonly"))
        await call.answer(text="Done")


    elif call.data.startswith("mute2_"):
        with suppress(MessageCantBeDeleted, MessageToDeleteNotFound):
            await call.message.bot.delete_message(config.groups.main, int(call.data.split("_")[1]))
            
        await call.message.bot.restrict_chat_member(chat_id=config.groups.main, user_id=call.data.split("_")[2],
                                                    permissions=types.ChatPermissions(),
                                                    until_date=int(time()) + ((3600 * 24) * 7))  # 7 days from now
        await call.message.bot.edit_message_text(chat_id=config.groups.reports,
                                                 message_id=call.message.message_id,
                                                 text=call.message.text + localization.get_string(
                                                     "action_deleted_readonly2"))
        await call.answer(text="Done")

    elif call.data.startswith("dismiss_"):
        await call.message.bot.edit_message_text(chat_id=config.groups.reports,
                                                 message_id=call.message.message_id,
                                                 text=call.message.text + localization.get_string(
                                                     "action_dismissed"))
        await call.answer(text="Done")

    elif call.data.startswith("dismiss2_"):
        with suppress(MessageCantBeDeleted, MessageToDeleteNotFound):
            await call.message.bot.delete_message(config.groups.main, int(call.data.split("_")[1]))

        await call.message.bot.restrict_chat_member(chat_id=config.groups.main, user_id=call.data.split("_")[2],
                                                    permissions=types.ChatPermissions(),
                                                    until_date=int(time()) + ((3600 * 24)))  # 1 day from now
        await call.message.bot.edit_message_text(chat_id=config.groups.reports,
                                                 message_id=call.message.message_id,
                                                 text=call.message.text + localization.get_string(
                                                     "action_deleted_dismissed2"))
        await call.answer(text="Done")
    elif call.data.startswith("dismiss3_"):
        with suppress(MessageCantBeDeleted, MessageToDeleteNotFound):
            await call.message.bot.delete_message(config.groups.main, int(call.data.split("_")[1]))

        await call.message.bot.restrict_chat_member(chat_id=config.groups.main, user_id=call.data.split("_")[2],
                                                    permissions=types.ChatPermissions(),
                                                    until_date=int(time()) + ((3600 * 24) * 7))  # 7 days from now
        await call.message.bot.edit_message_text(chat_id=config.groups.reports,
                                                 message_id=call.message.message_id,
                                                 text=call.message.text + localization.get_string(
                                                     "action_deleted_dismissed3"))
        await call.answer(text="Done")
    elif call.data.startswith("dismiss4_"):
        with suppress(MessageCantBeDeleted, MessageToDeleteNotFound):
            await call.message.bot.delete_message(config.groups.main, int(call.data.split("_")[1]))

        await call.message.bot.kick_chat_member(chat_id=config.groups.main, user_id=call.data.split("_")[2])
        await call.message.bot.edit_message_text(chat_id=config.groups.reports,
                                                 message_id=call.message.message_id,
                                                 text=call.message.text + localization.get_string(
                                                     "action_deleted_dismissed4"))
        await call.answer(text="Done")

    ###
    ### SPAM callbacks
    ###
    elif call.data.startswith("spam_test_"):
        # delete record
        await Spam.objects.delete(id=int(call.data.split("_")[2]))

        # increase member messages count, cuz is not a spam :3
        member = await Member.objects.get(id=int(call.data.split("_")[3]))
        member.messages_count += 1
        await member.update()

        await call.message.bot.edit_message_text(chat_id=config.groups.logs,
                                                 message_id=call.message.message_id,
                                                 text=call.message.text + "\n\n<b>Удалено из базы, вероятно тест.</b>")
        await call.answer(text="Done")
    elif call.data.startswith("spam_ban_"):
        with suppress(CantRestrictChatOwner):
            await call.message.bot.kick_chat_member(chat_id=config.groups.main, user_id=call.data.split("_")[2])

        await call.message.bot.edit_message_text(chat_id=config.groups.logs,
                                                 message_id=call.message.message_id,
                                                 text=call.message.text + "\n\n❌ <b>Юзер забанен, сообщение помечено как спам</b>")
        await call.answer(text="Done")
    elif call.data.startswith("spam_invert_"):
        # retrieve record
        spam_rec = await Spam.objects.get(id=int(call.data.split("_")[2]))
        spam_rec.is_spam = False
        await spam_rec.update()

        await call.message.bot.edit_message_text(chat_id=config.groups.logs,
                                                 message_id=call.message.message_id,
                                                 text=call.message.text + "\n\n❎ <b>Сообщение помечено как НЕ СПАМ</b>")
