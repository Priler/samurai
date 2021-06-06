from time import time
from aiogram import types
from aiogram.dispatcher.filters import Text
from configurator import config
from dispatcher import dp
import localization
import utils
import random

@dp.message_handler(chat_id=config.groups.main, commands="report", commands_prefix="/!")
async def cmd_report(message: types.Message):
    # Check if command is sent as reply to some message
    if not message.reply_to_message:
        await message.reply(localization.get_string("error_no_reply"))
        return

    # Check if command is sent as reply to admin
    user = await message.bot.get_chat_member(config.groups.main, message.reply_to_message.from_user.id)
    if user.is_chat_admin():
        await message.reply(localization.get_string("error_report_admin"))
        return

    # Cannot report group posts
    if message.reply_to_message.from_user.id == 777000:
        await message.bot.delete_message(config.groups.main, message.message_id)
        return

    # Check for report message (anything sent after /report or !report command)
    msg_parts = message.text.split()
    report_message = None
    if len(msg_parts) > 1:
        report_message = message.text.replace("!report", "")
        report_message = report_message.replace("/report", "")

    # Generate keyboard with some actions
    action_keyboard = types.InlineKeyboardMarkup()
    # Delete message by its id
    action_keyboard.add(types.InlineKeyboardButton(
        text=localization.get_string("action_del_msg"),
        callback_data=f"del_{message.reply_to_message.message_id}")
    )

    # Delete message by its id and ban user by their id
    action_keyboard.add(types.InlineKeyboardButton(
        text=localization.get_string("action_del_and_ban"),
        callback_data=f"delban_{message.reply_to_message.message_id}_{message.reply_to_message.from_user.id}"
    ))

    # Delete message by its id and mute user for 24 hours by their id
    action_keyboard.add(types.InlineKeyboardButton(
        text=localization.get_string("action_del_and_readonly"),
        callback_data=f"mute_{message.reply_to_message.message_id}_{message.reply_to_message.from_user.id}"
    ))

    # Delete message by its id and mute user for 7 days by their id
    action_keyboard.add(types.InlineKeyboardButton(
        text=localization.get_string("action_del_and_readonly2"),
        callback_data=f"mute2_{message.reply_to_message.message_id}_{message.reply_to_message.from_user.id}"
    ))

    # Do nothing, false alarm
    action_keyboard.add(types.InlineKeyboardButton(
        text=localization.get_string("action_false_alarm"),
        callback_data=f"dismiss_{message.reply_to_message.message_id}_{message.reply_to_message.from_user.id}"
    ))

    await message.reply_to_message.forward(config.groups.reports)
    await message.bot.send_message(
        config.groups.reports,
        utils.get_report_comment(
            message.reply_to_message.date,
            message.reply_to_message.message_id,
            report_message
        ),
        reply_markup=action_keyboard)
    await message.reply(localization.get_string("report_delivered"))

@dp.message_handler(Text(startswith="@admin", ignore_case=True), chat_id=config.groups.main)
async def calling_all_units(message: types.Message):
    """
    Handler which is triggered when message starts with @admin.
    Honestly any combination will work: @admin, @admins, @adminisshit

    :param message: Telegram message where text starts with @admin
    """
    await message.bot.send_message(
        config.groups.reports,
        localization.get_string("need_admins_attention").format(
            chat_id=utils.get_url_chat_id(config.groups.main),
            msg_id=message.reply_to_message.message_id
            if message.reply_to_message
            else message.message_id
        )
    )
