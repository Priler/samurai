"""Join events and cleanup of low-reputation users' reactions."""
import logging

from aiogram import Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ChatMemberUpdated, MessageReactionUpdated

from config import config
from services import reactions
from services.cache import retrieve_or_create_member, invalidate_tgmember_cache
from utils.enums import MemberStatus

router = Router(name="reactions")
logger = logging.getLogger(__name__)


@router.chat_member()
async def on_member_update(event: ChatMemberUpdated) -> None:
    if event.chat.type != "supergroup" or not config.groups.is_main_group(event.chat.id):
        return
    user = event.new_chat_member.user
    if user.is_bot:
        return
    invalidate_tgmember_cache(event.chat.id, user.id)
    await reactions.sync_member(event.bot, event.chat.id, user.id, force=True)


@router.message_reaction()
async def on_reaction(event: MessageReactionUpdated) -> None:
    if (not config.reactions.enabled or event.chat.type != "supergroup"
            or not config.groups.is_main_group(event.chat.id)
            or event.user is None or event.user.is_bot or not event.new_reaction):
        return
    try:
        role = await reactions.lookup_member(event.bot, event.chat.id, event.user.id)
        if role is None or role.status in MemberStatus.admin_statuses():
            return
        member = await retrieve_or_create_member(event.user.id)
        await reactions.sync_member(event.bot, event.chat.id, event.user.id, force=True)
        if member.reputation_points >= config.reactions.rep_threshold:
            return
        # Remove the reaction even if applying the future restriction failed.
        await event.bot.delete_message_reaction(
            chat_id=event.chat.id, message_id=event.message_id, user_id=event.user.id,
        )
        logger.info("Removed low-reputation reaction from user %s in chat %s on message %s",
                    event.user.id, event.chat.id, event.message_id)
    except TelegramAPIError:
        logger.exception("Failed to remove reaction from user %s in chat %s",
                         event.user.id, event.chat.id)
