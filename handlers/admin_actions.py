from time import time
from aiogram import types
from configurator import config
from dispatcher import dp
import localization
import utils

'''@dp.message_handler(is_admin=True, chat_id=config.groups.main, commands="mute", commands_prefix="!")
async def cmd_readonly(message: types.Message):
    """
    Handler for /ro command in chat.
    Reports which are not replies are ignored.
    Only admins can use this command. A time period may be set after command, f.ex. /ro 2d,
    anything else is treated as commentary with no effect.

    :param message: Telegram message with /ro command and optional time
    """
    # Check if command is sent as reply to some message
    #if not message.reply_to_message:
    #    await message.reply(localization.get_string("error_no_reply"))
    #    return

    # Check if command is sent as reply to some message
    if not message.reply_to_message:
        await message.reply(localization.get_string("error_no_reply"))
        return

    # Admins cannot be restricted
    user = await message.bot.get_chat_member(config.groups.main, message.reply_to_message.from_user.id)
    if user.is_chat_admin():
        await message.reply(localization.get_string("error_restrict_admin"))
        return

    words = message.text.split()
    restriction_time: int = 0
    if len(words) > 1:  # !mute with arg
        restriction_time = utils.get_restriction_time(words[1])
        if not restriction_time:
            await message.reply(localization.get_string("error_wrong_time_format"))
            return
    else:
    	restriction_time = 86400 * 367

    await message.bot.restrict_chat_member(config.groups.main,
                                           message.reply_to_message.from_user.id,
                                           types.ChatPermissions(),
                                           until_date=int(time()) + restriction_time
                                           )

    if len(words) > 1:
    	await message.reply(localization.get_string("resolved_readonly").format(restriction_time=words[1]))
    else:
    	await message.reply(localization.get_string("restriction_forever"))

@dp.message_handler(is_admin=True, chat_id=config.groups.main, commands="unmute", commands_prefix="!")
async def cmd_unreadonly(message: types.Message):
    """
    Handler for /ro command in chat.
    Reports which are not replies are ignored.
    Only admins can use this command. A time period may be set after command, f.ex. /ro 2d,
    anything else is treated as commentary with no effect.

    :param message: Telegram message with /ro command and optional time
    """
    # Check if command is sent as reply to some message
    #if not message.reply_to_message:
    #    await message.reply(localization.get_string("error_no_reply"))
    #    return

    # Check if command is sent as reply to some message
    if not message.reply_to_message:
        await message.reply(localization.get_string("error_no_reply"))
        return

    # Admins cannot be restricted
    user = await message.bot.get_chat_member(config.groups.main, message.reply_to_message.from_user.id)
    if user.is_chat_admin():
        await message.reply(localization.get_string("error_restrict_admin"))
        return

    words = message.text.split()
    restriction_time: int = 0
    if len(words) > 1:  # /ro with arg
        restriction_time = utils.get_restriction_time(words[1])
        if not restriction_time:
            await message.reply(localization.get_string("error_wrong_time_format"))
            return

    await message.bot.restrict_chat_member(config.groups.main,
                                           message.reply_to_message.from_user.id,
                                           types.ChatPermissions(True))
    
    await message.reply(localization.get_string("user_unmuted"))'''

'''@dp.message_handler(is_admin=True, chat_id=config.groups.main, commands=["givemedia"], commands_prefix="!")
async def cmd_givemedia(message: types.Message):
    # Check if command is sent as reply to some message
    if not message.reply_to_message:
        await message.reply(localization.get_string("error_no_reply"))
        return

    # Admins cannot be restricted
    user = await message.bot.get_chat_member(config.groups.main, message.reply_to_message.from_user.id)
    if user.is_chat_admin():
        await message.reply(localization.get_string("error_givemedia_admin"))
        return

    words = message.text.split()
    restriction_time: int = 0
    if len(words) > 1:  # /ro with arg
        restriction_time = utils.get_restriction_time(words[1])
        if not restriction_time:
            await message.reply(localization.get_string("error_wrong_time_format"))
            return
    else:
    	restriction_time = 86400 * 367

    await message.bot.restrict_chat_member(
        config.groups.main,
        message.reply_to_message.from_user.id,
        types.ChatPermissions(can_send_messages=user.can_send_messages, can_send_media_messages=True, can_send_other_messages=True),
        until_date=int(time()) + restriction_time)


    if len(words) > 1:
    	await message.reply(localization.get_string("resolved_givemedia").format(restriction_time=words[1]))
    else:
    	await message.reply(localization.get_string("resolved_givemedia_forever"))

@dp.message_handler(is_admin=True, chat_id=config.groups.main, commands=["revokemedia"], commands_prefix="!")
async def cmd_revokemedia(message: types.Message):
    # Check if command is sent as reply to some message
    if not message.reply_to_message:
        await message.reply(localization.get_string("error_no_reply"))
        return

    # Admins cannot be restricted
    user = await message.bot.get_chat_member(config.groups.main, message.reply_to_message.from_user.id)
    if user.is_chat_admin():
        await message.reply(localization.get_string("error_restrict_admin"))
        return

    words = message.text.split()
    restriction_time: int = 0
    if len(words) > 1:  # /ro with arg
        restriction_time = utils.get_restriction_time(words[1])
        if not restriction_time:
            await message.reply(localization.get_string("error_wrong_time_format"))
            return
    else:
    	restriction_time = 86400 * 367

    await message.bot.restrict_chat_member(
        config.groups.main,
        message.reply_to_message.from_user.id,
        types.ChatPermissions(can_send_messages=user.can_send_messages, can_send_media_messages=False, can_send_other_messages=False),
        until_date=int(time()) + restriction_time)

    if len(words) > 1:
    	await message.reply(localization.get_string("resolved_nomedia").format(restriction_time=words[1]))
    else:
    	await message.reply(localization.get_string("resolved_nomedia_forever"))'''

'''@dp.message_handler(is_admin=True, chat_id=config.groups.main, commands=["checkperms"], commands_prefix="!")
async def cmd_checkperms(message: types.Message):
    # Check if command is sent as reply to some message
    if not message.reply_to_message:
        await message.reply(localization.get_string("error_no_reply"))
        return
    
    # Check if command is sent as reply to some message
    if not message.reply_to_message:
        await message.reply(localization.get_string("error_no_reply"))
        return

    # check if member is admin
    user = await message.bot.get_chat_member(config.groups.main, message.reply_to_message.from_user.id)
    if user.is_chat_admin():
        await message.reply(localization.get_string("error_checkperms_admin"))
        return


    msg = "Текущие права:\n"

    if(user.can_send_messages is None):
    	# default chat perms
    	chat = await message.bot.get_chat(message.chat.id)

    	msg += "\nОтправлять сообщения: " + ("✅" if chat.permissions.can_send_messages else "❌")
    	msg += "\nОтправлять медиа: " + ("✅" if chat.permissions.can_send_media_messages else "❌")
    	msg += "\nОтправлять стикеры: " + ("✅" if chat.permissions.can_send_other_messages else "❌")
    else:
    	# custom perms
    	msg += "\nОтправлять сообщения: " + ("✅" if user.can_send_messages else "❌")
    	msg += "\nОтправлять медиа: " + ("✅" if user.can_send_media_messages else "❌")
    	msg += "\nОтправлять стикеры: " + ("✅" if user.can_send_other_messages else "❌")


    await message.reply(msg)'''

@dp.message_handler(member_can_restrict=True, chat_id=config.groups.main, commands=["ban"], commands_prefix="!/")
async def cmd_ban(message: types.Message):
    # Check if command is sent as reply to some message
    if not message.reply_to_message:
        await message.reply(localization.get_string("error_no_reply"))
        return

    # Admins cannot be restricted
    user = await message.bot.get_chat_member(config.groups.main, message.reply_to_message.from_user.id)
    if user.is_chat_admin():
        await message.reply(localization.get_string("error_ban_admin"))
        return

    await message.bot.delete_message(config.groups.main, message.message_id)  # remove admin message
    await message.bot.kick_chat_member(chat_id=config.groups.main, user_id=message.reply_to_message.from_user.id)

    await message.reply_to_message.reply(localization.get_string("resolved_ban"))


@dp.message_handler(member_can_restrict=True, chat_id=config.groups.main, commands=["unban"], commands_prefix="!/")
async def cmd_unban(message: types.Message):
    # Check if command is sent as reply to some message
    if not message.reply_to_message:
        await message.reply(localization.get_string("error_no_reply"))
        return

    # Admins cannot be restricted
    user = await message.bot.get_chat_member(config.groups.main, message.reply_to_message.from_user.id)
    if user.is_chat_admin():
        await message.reply(localization.get_string("error_ban_admin"))
        return

    await message.bot.delete_message(config.groups.main, message.message_id)  # remove admin message
    await message.bot.unban_chat_member(chat_id=config.groups.main, user_id=message.reply_to_message.from_user.id)

    await message.reply_to_message.reply(localization.get_string("resolved_unban"))


'''@dp.message_handler(is_admin=True, chat_id=config.groups.main, commands=["ro"], commands_prefix="!")
async def cmd_ro(message: types.Message):
    """
    Handler for /ro command.
    Requires a callback in group_events.py
    """
    if(builtins.RO):
        # disable RO
        builtins.RO = False
        await message.reply(localization.get_string("disabled_ro"))
    else:
        # enable RO
        builtins.RO = True
        await message.reply(localization.get_string("enabled_ro"))'''
