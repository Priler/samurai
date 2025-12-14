"""
Admin action handlers (ban, unban, etc.).
"""
from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from config import config
from db.models import Member
from filters import MemberCanRestrictFilter, InMainGroups, IsAdminFilter
from utils import get_string, MemberStatus, user_mention_by_id

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


def _parse_count(command: CommandObject, default: int = 10, max_val: int = 50) -> int:
    """Parse count argument from command, with bounds."""
    if not command.args:
        return default
    try:
        count = int(command.args.strip())
        return max(1, min(count, max_val))
    except ValueError:
        return default


@router.message(
    InMainGroups(),
    IsAdminFilter(),
    Command("top_violators_profanity", prefix="!/")
)
async def cmd_top_violators_profanity(message: Message, command: CommandObject) -> None:
    """
    Show top profanity violators.
    
    Usage: /top_violators_profanity [count]
    Default count: 10, Max: 50
    """
    count = _parse_count(command)
    
    # Query database
    violators = await Member.objects.filter(
        violations_count_profanity__gt=0
    ).order_by("-violations_count_profanity").limit(count).all()
    
    if not violators:
        await message.reply("🧼 Нарушителей не найдено")
        return
    
    # Build response
    lines = [f"🤬 <b>Топ-{len(violators)} нарушителей (мат):</b>\n"]
    
    for i, member in enumerate(violators, 1):
        lines.append(
            f"{i}. {user_mention_by_id(member.user_id)} — "
            f"<b>{member.violations_count_profanity}</b> нарушений"
        )
    
    await message.reply("\n".join(lines))


@router.message(
    InMainGroups(),
    IsAdminFilter(),
    Command("top_violators_spam", prefix="!/")
)
async def cmd_top_violators_spam(message: Message, command: CommandObject) -> None:
    """
    Show top spam violators.
    
    Usage: /top_violators_spam [count]
    Default count: 10, Max: 50
    """
    count = _parse_count(command)
    
    # Query database
    violators = await Member.objects.filter(
        violations_count_spam__gt=0
    ).order_by("-violations_count_spam").limit(count).all()
    
    if not violators:
        await message.reply("🧼 Нарушителей не найдено")
        return
    
    # Build response
    lines = [f"📨 <b>Топ-{len(violators)} нарушителей (спам):</b>\n"]
    
    for i, member in enumerate(violators, 1):
        lines.append(
            f"{i}. {user_mention_by_id(member.user_id)} — "
            f"<b>{member.violations_count_spam}</b> нарушений"
        )
    
    await message.reply("\n".join(lines))
