"""
Throttling middleware for rate limiting.

Prevents spam in private chats by limiting message frequency.
"""
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from cachetools import TTLCache


class ThrottlingMiddleware(BaseMiddleware):
    """
    Rate limiting middleware for private chats.
    
    Limits users to a certain number of messages per time period.
    Only applies to private chats, not groups.
    """
    
    def __init__(
        self,
        rate_limit: float = 0.5,  # Minimum seconds between messages
        max_messages: int = 20,   # Max messages in time window
        time_window: int = 60     # Time window in seconds
    ) -> None:
        """
        Initialize throttling middleware.
        
        Args:
            rate_limit: Minimum time between messages (seconds)
            max_messages: Maximum messages allowed in time window
            time_window: Time window for max_messages limit (seconds)
        """
        self.rate_limit = rate_limit
        self.max_messages = max_messages
        self.time_window = time_window
        
        # Cache for last message time per user
        self.last_message_cache: TTLCache = TTLCache(
            maxsize=10000,
            ttl=rate_limit * 2
        )
        
        # Cache for message count per user
        self.message_count_cache: TTLCache = TTLCache(
            maxsize=10000,
            ttl=time_window
        )
        
        super().__init__()
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """Process event with rate limiting."""
        # Only apply to messages
        if not isinstance(event, Message):
            return await handler(event, data)
        
        # Only apply to private chats
        if event.chat.type != "private":
            return await handler(event, data)
        
        user_id = event.from_user.id
        
        # Check rate limit (time between messages)
        import time
        current_time = time.time()
        last_time = self.last_message_cache.get(user_id, 0)
        
        if current_time - last_time < self.rate_limit:
            # Too fast, ignore message
            return None
        
        # Check message count limit
        count = self.message_count_cache.get(user_id, 0)
        if count >= self.max_messages:
            # Too many messages, send warning once
            if count == self.max_messages:
                await event.answer(
                    "⚠️ Слишком много сообщений. Подождите немного."
                )
            self.message_count_cache[user_id] = count + 1
            return None
        
        # Update caches
        self.last_message_cache[user_id] = current_time
        self.message_count_cache[user_id] = count + 1
        
        return await handler(event, data)
