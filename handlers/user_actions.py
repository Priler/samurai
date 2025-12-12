"""
User action handlers (report, @admin).
"""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from config import config
from filters import InMainGroups
from services.reports import is_already_reported, track_report
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

    reported_msg = message.reply_to_message
    chat_id = message.chat.id
    
    # Delete the /report command message immediately
    try:
        await message.delete()
    except Exception:
        pass

    # Can't report yourself
    if reported_msg.from_user.id == message.from_user.id:
        return

    # Can't report admins
    user = await message.bot.get_chat_member(chat_id, reported_msg.from_user.id)
    if user.status in MemberStatus.admin_statuses():
        return

    # Can't report channel posts (user 777000)
    if reported_msg.from_user.id == 777000:
        return

    # Check if already reported
    if is_already_reported(chat_id, reported_msg.message_id):
        return  # Already reported, just return silently

    # Track this report
    track_report(chat_id, reported_msg.message_id)

    # Check for report message (anything after /report)
    msg_parts = message.text.split(maxsplit=1)
    report_message = msg_parts[1] if len(msg_parts) > 1 else None

    # Reply to the REPORTED message with "under review" 
    bot_reply = await reported_msg.reply(_random("report-under-review"))
    
    # Build callback data with all needed info:
    # Format: action_chatId_reportedMsgId_reportedUserId_reporterUserId_botReplyMsgId
    reply_msg_id = reported_msg.message_id
    reply_user_id = reported_msg.from_user.id
    reporter_user_id = message.from_user.id
    bot_reply_id = bot_reply.message_id

    # Callback data helper - all actions need chat_id, msg_id, user_id, reporter_id, bot_reply_id
    def cb(action: str, include_user: bool = True) -> str:
        if include_user:
            return f"{action}_{chat_id}_{reply_msg_id}_{reply_user_id}_{reporter_user_id}_{bot_reply_id}"
        return f"{action}_{chat_id}_{reply_msg_id}_{reporter_user_id}_{bot_reply_id}"

    # Generate link to message
    url_chat_id = get_url_chat_id(chat_id)
    message_url = f"https://t.me/c/{url_chat_id}/{reply_msg_id}"

    action_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=get_string("action_go_to_message"),
            url=message_url
        )],
        [InlineKeyboardButton(
            text=get_string("action_del_msg"),
            callback_data=cb("rdel", include_user=False)
        )],
        [InlineKeyboardButton(
            text=get_string("action_del_and_ban"),
            callback_data=cb("rdelban")
        )],
        [InlineKeyboardButton(
            text=get_string("action_del_and_readonly"),
            callback_data=cb("rmute")
        )],
        [InlineKeyboardButton(
            text=get_string("action_del_and_readonly2"),
            callback_data=cb("rmute2")
        )],
        [InlineKeyboardButton(
            text=get_string("action_false_alarm"),
            callback_data=cb("rdismiss")
        )],
        [InlineKeyboardButton(
            text=get_string("action_false_alarm_2"),
            callback_data=cb("rdismiss2")
        )],
        [InlineKeyboardButton(
            text=get_string("action_false_alarm_3"),
            callback_data=cb("rdismiss3")
        )],
        [InlineKeyboardButton(
            text=get_string("action_false_alarm_4"),
            callback_data=cb("rdismiss4")
        )]
    ])

    # Forward reported message and send report to admins
    await reported_msg.forward(config.groups.reports)
    await message.bot.send_message(
        config.groups.reports,
        get_report_comment(
            reported_msg.date,
            reported_msg.message_id,
            chat_id,
            report_message,
            message.chat.title,
            reporter=message.from_user
        ),
        reply_markup=action_keyboard
    )


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

    # format report message
    header = f"[ {message.chat.title} ]\n\n" if message.chat.title else ""

    await message.bot.send_message(
        config.groups.reports,
        header + get_string(
            "need_admins_attention",
            chat_id=get_url_chat_id(message.chat.id),
            msg_id=msg_id
        )
    )
