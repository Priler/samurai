"""
Admin action handlers (ban, unban, etc.).
"""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from config import config
from filters import MemberCanRestrictFilter, InMainGroups
from utils import get_string, MemberStatus

router = Router(name="admin_actions")


@router.message(
    InMainGroups(),
    MemberCanRestrictFilter(),
    Command("ban", prefix="!/")
)
async def cmd_ban(message: Message) -> None:
    """Ban a user (reply to their message)."""
    if not message.reply_to_message:
        await message.reply(get_string("error_no_reply"))
        return

    # Admins cannot be banned
    user = await message.bot.get_chat_member(
        message.chat.id,
        message.reply_to_message.from_user.id
    )
    if user.status in MemberStatus.admin_statuses():
        await message.reply(get_string("error_ban_admin"))
        return

    # Remove admin's command message
    await message.delete()

    # Ban the user
    await message.bot.ban_chat_member(
        chat_id=message.chat.id,
        user_id=message.reply_to_message.from_user.id
    )

    await message.reply_to_message.reply(get_string("resolved_ban"))


@router.message(
    InMainGroups(),
    MemberCanRestrictFilter(),
    Command("unban", prefix="!/")
)
async def cmd_unban(message: Message) -> None:
    """Unban a user (reply to their message)."""
    if not message.reply_to_message:
        await message.reply(get_string("error_no_reply"))
        return

    # Admins cannot be unbanned
    user = await message.bot.get_chat_member(
        message.chat.id,
        message.reply_to_message.from_user.id
    )
    if user.status in MemberStatus.admin_statuses():
        await message.reply(get_string("error_ban_admin"))
        return

    # Remove admin's command message
    await message.delete()

    # Unban the user
    await message.bot.unban_chat_member(
        chat_id=message.chat.id,
        user_id=message.reply_to_message.from_user.id
    )

    await message.reply_to_message.reply(get_string("resolved_unban"))
