"""Keep reaction permissions aligned with reputation around message handlers."""
from aiogram import BaseMiddleware
from aiogram.types import Message

from config import config
from services import reactions


class ReactionsMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if (not config.reactions.enabled or not reactions.is_running() or not isinstance(event, Message)
                or event.chat.type != "supergroup"
                or not config.groups.is_main_group(event.chat.id)
                or event.from_user is None or event.from_user.is_bot
                or event.sender_chat is not None or event.is_automatic_forward):
            return await handler(event, data)
        await reactions.sync_member(event.bot, event.chat.id, event.from_user.id)
        try:
            return await handler(event, data)
        finally:
            # This also covers command handlers and messages deleted by moderation.
            await reactions.sync_member(event.bot, event.chat.id, event.from_user.id)
