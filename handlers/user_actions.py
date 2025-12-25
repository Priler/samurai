"""
User action handlers (report, @admin).
"""
import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from config import config
from filters import InMainGroups
from services.reports import is_already_reported, track_report
from utils import get_string, _random, get_report_comment, get_url_chat_id, MemberStatus

router = Router(name="user_actions")
logger = logging.getLogger(__name__)


@router.message(
    InMainGroups(),
    Command("report", "репорт", prefix="!/")
)
async def cmd_report(message: Message) -> None:
    """Report a message to admins."""
    # check if reply
    if not message.reply_to_message:
        await message.reply(get_string("error-no-reply"))
        return

    reported_msg = message.reply_to_message
    chat_id = message.chat.id

    # can't report yourself
    if reported_msg.from_user.id == message.from_user.id:
        await message.reply(get_string("error-report-self"))
        return

    # can't report admins
    try:
        user = await message.bot.get_chat_member(chat_id, reported_msg.from_user.id)
        if user.status in MemberStatus.admin_statuses():
            await message.reply(get_string("error-report-admin"))
            return
    except Exception:
        pass  # user might have left, continue with report

    # can't report channel posts (user 777000)
    if reported_msg.from_user.id == 777000:
        try:
            await message.delete()
        except Exception:
            pass
        return

    # check if already reported
    if is_already_reported(chat_id, reported_msg.message_id):
        # already being handled - already being handled
        try:
            await message.delete()
        except Exception:
            pass
        return

    # track this report
    track_report(chat_id, reported_msg.message_id)

    # check for report message (anything after /report)
    msg_parts = message.text.split(maxsplit=1)
    report_message = msg_parts[1] if len(msg_parts) > 1 else None

    # reply to reported msg with "under review" 
    try:
        bot_reply = await reported_msg.reply(_random("report-under-review"), parse_mode="HTML")
    except Exception as e:
        # can't reply - maybe deleted (maybe deleted?)
        logger.warning(f"Failed to reply to reported message: {e}")
        return
    
    # delete the /report command after successful reply
    try:
        await message.delete()
    except Exception:
        pass

    # build callback data:
    # format: action_chatId_reportedMsgId_reportedUserId_reporterUserId_botReplyMsgId
    reply_msg_id = reported_msg.message_id
    reply_user_id = reported_msg.from_user.id
    reporter_user_id = message.from_user.id
    bot_reply_id = bot_reply.message_id

    # callback data helper - all actions need chat_id, msg_id, user_id, reporter_id, bot_reply_id
    def cb(action: str, include_user: bool = True) -> str:
        if include_user:
            return f"{action}_{chat_id}_{reply_msg_id}_{reply_user_id}_{reporter_user_id}_{bot_reply_id}"
        return f"{action}_{chat_id}_{reply_msg_id}_{reporter_user_id}_{bot_reply_id}"

    # generate link
    url_chat_id = get_url_chat_id(chat_id)
    message_url = f"https://t.me/c/{url_chat_id}/{reply_msg_id}"

    action_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=get_string("action-go-to-message"),
            url=message_url
        )],
        [InlineKeyboardButton(
            text=get_string("action-del-msg"),
            callback_data=cb("rdel", include_user=False)
        )],
        [InlineKeyboardButton(
            text=get_string("action-del-and-ban"),
            callback_data=cb("rdelban")
        )],
        [InlineKeyboardButton(
            text=get_string("action-del-and-readonly"),
            callback_data=cb("rmute")
        )],
        [InlineKeyboardButton(
            text=get_string("action-del-and-readonly2"),
            callback_data=cb("rmute2")
        )],
        [InlineKeyboardButton(
            text=get_string("action-false-alarm"),
            callback_data=cb("rdismiss")
        )],
        [InlineKeyboardButton(
            text=get_string("action-false-alarm-2"),
            callback_data=cb("rdismiss2")
        )],
        [InlineKeyboardButton(
            text=get_string("action-false-alarm-3"),
            callback_data=cb("rdismiss3")
        )],
        [InlineKeyboardButton(
            text=get_string("action-false-alarm-4"),
            callback_data=cb("rdismiss4")
        )]
    ])

    # forward and send to admins
    try:
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
            parse_mode="HTML",
            reply_markup=action_keyboard
        )
    except Exception as e:
        logger.error(f"Failed to send report to admin channel: {e}")


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

    try:
        await message.bot.send_message(
            config.groups.reports,
            header + get_string(
                "need-admins-attention",
                chat_id=get_url_chat_id(message.chat.id),
                msg_id=msg_id
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to send @admin alert: {e}")
