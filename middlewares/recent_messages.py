"""Track group messages for retrospective moderation cleanup."""
from typing import Any, Awaitable, Callable, Dict
import asyncio
from weakref import WeakValueDictionary

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from config import config
from services.recent_messages import track_recent_message, delete_recent_messages, delete_message_if_present
from services.cache import get_cached_nsfw_profile_result, retrieve_tgmember
from services.bot_names import enforce_learned_name
from utils.enums import MemberStatus


class RecentMessagesMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        # Waiting tasks keep a lock alive; idle users leave no registry entries
        self._user_locks: WeakValueDictionary = WeakValueDictionary()
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if (
            isinstance(event, Message)
            and event.from_user is not None
            and event.sender_chat is None
            and not event.is_automatic_forward
            and config.groups.is_main_group(event.chat.id)
        ):
            # Track on arrival, before waiting for the user's first ML check
            track_recent_message(event.chat.id, event.from_user.id, event.message_id)
            key = (event.chat.id, event.from_user.id)
            lock = self._user_locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._user_locks[key] = lock
            async with lock:
                if (config.nsfw.enabled
                        and get_cached_nsfw_profile_result(event.from_user.id) in ("soft", "hard")):
                    member = await retrieve_tgmember(event.bot, *key)
                    if member.status not in MemberStatus.admin_statuses():
                        await delete_message_if_present(event)
                        await delete_recent_messages(
                            event.bot, *key, exclude_message_id=event.message_id,
                        )
                        return None
                if await enforce_learned_name(event):
                    return None
                return await handler(event, data)
        return await handler(event, data)
