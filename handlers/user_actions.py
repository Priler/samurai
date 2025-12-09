"""
User action handlers (report, @admin).
"""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from config import config
from filters import InMainGroups
from utils import get_string, _random, get_report_comment, get_url_chat_id, MemberStatus

router = Router(name="user_actions")


@router.message(
    InMainGroups(),
    Command("report", "репорт", prefix="!/")
)
async def cmd_report(message: Message) -> None:
    """Report a message to admins."""
    # Check if command is sent as reply
    if not message.reply_to_message:
        await message.reply(get_string("error_no_reply"))
        return

    # Can't report yourself
    if message.reply_to_message.from_user.id == message.from_user.id:
        await message.reply(get_string("error_report_self"))
        return

    # Can't report admins
    user = await message.bot.get_chat_member(
        message.chat.id,
        message.reply_to_message.from_user.id
    )
    if user.status in MemberStatus.admin_statuses():
        await message.reply(get_string("error_report_admin"))
        return

    # Can't report channel posts (user 777000)
    if message.reply_to_message.from_user.id == 777000:
        await message.delete()
        return

    # Check for report message (anything after /report)
    msg_parts = message.text.split(maxsplit=1)
    report_message = msg_parts[1] if len(msg_parts) > 1 else None

    # Generate keyboard with actions
    # Include chat_id in callback_data for multi-group support
    chat_id = message.chat.id
    reply_msg_id = message.reply_to_message.message_id
    reply_user_id = message.reply_to_message.from_user.id
    reporter_msg_id = message.message_id
    reporter_user_id = message.from_user.id

    action_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=get_string("action_del_msg"),
            callback_data=f"del_{chat_id}_{reply_msg_id}"
        )],
        [InlineKeyboardButton(
            text=get_string("action_del_and_ban"),
            callback_data=f"delban_{chat_id}_{reply_msg_id}_{reply_user_id}"
        )],
        [InlineKeyboardButton(
            text=get_string("action_del_and_readonly"),
            callback_data=f"mute_{chat_id}_{reply_msg_id}_{reply_user_id}"
        )],
        [InlineKeyboardButton(
            text=get_string("action_del_and_readonly2"),
            callback_data=f"mute2_{chat_id}_{reply_msg_id}_{reply_user_id}"
        )],
        [InlineKeyboardButton(
            text=get_string("action_false_alarm"),
            callback_data=f"dismiss_{chat_id}_{reply_msg_id}_{reply_user_id}"
        )],
        [InlineKeyboardButton(
            text=get_string("action_false_alarm_2"),
            callback_data=f"dismiss2_{chat_id}_{reporter_msg_id}_{reporter_user_id}"
        )],
        [InlineKeyboardButton(
            text=get_string("action_false_alarm_3"),
            callback_data=f"dismiss3_{chat_id}_{reporter_msg_id}_{reporter_user_id}"
        )],
        [InlineKeyboardButton(
            text=get_string("action_false_alarm_4"),
            callback_data=f"dismiss4_{chat_id}_{reporter_msg_id}_{reporter_user_id}"
        )]
    ])

    # Forward reported message and send report
    await message.reply_to_message.forward(config.groups.reports)
    await message.bot.send_message(
        config.groups.reports,
        get_report_comment(
            message.reply_to_message.date,
            message.reply_to_message.message_id,
            chat_id,
            report_message,
            message.chat.title
        ),
        reply_markup=action_keyboard
    )

    await message.reply(_random("report-responses"))


@router.message(
    InMainGroups(),
    F.text.lower().startswith("@admin")
)
async def calling_all_units(message: Message) -> None:
    """Handle @admin mentions."""
    msg_id = (
        message.reply_to_message.message_id
        if message.reply_to_message
        else message.message_id
    )

    # Include chat name in the message
    header = f"🟢 <b>{message.chat.title}</b>\n\n" if message.chat.title else ""

    await message.bot.send_message(
        config.groups.reports,
        header + get_string(
            "need_admins_attention",
            chat_id=get_url_chat_id(message.chat.id),
            msg_id=msg_id
        )
    )
