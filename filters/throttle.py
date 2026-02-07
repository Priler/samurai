"""
Throttle filter for rate-limiting commands.

Usage:
    @router.message(ThrottleFilter(interval=60, per_group=True), Command("rules"))
    async def on_rules(message: Message) -> None:
        ...
"""
import time
from typing import Union

from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery
from cachetools import TTLCache


class ThrottleFilter(BaseFilter):
    """
    Filter that throttles command execution.
    
    Args:
        interval: Cooldown in seconds
        per_member: If True, throttle per user (default: False)
        per_group: If True, throttle per group/chat (default: False)
        
    If both per_member and per_group are True, throttles per user per group.
    If both are False, throttles globally for this filter instance.
    """
    
    def __init__(
        self, 
        interval: int = 60, 
        per_member: bool = False, 
        per_group: bool = False
    ) -> None:
        self.interval = interval
        self.per_member = per_member
        self.per_group = per_group
        # TTL-based storage so old entries are auto-evicted
        self._timestamps: TTLCache = TTLCache(maxsize=10000, ttl=interval)
    
    def _get_key(self, event: Union[Message, CallbackQuery]) -> tuple:
        """Generate throttle key based on settings."""
        group_id = 0
        user_id = 0
        
        if self.per_group:
            if isinstance(event, Message):
                group_id = event.chat.id
            elif event.message:
                group_id = event.message.chat.id
        
        if self.per_member:
            if event.from_user:
                user_id = event.from_user.id
        
        return (group_id, user_id)
    
    async def __call__(self, event: Union[Message, CallbackQuery]) -> bool:
        key = self._get_key(event)
        
        if key in self._timestamps:
            return False  # Throttled
        
        self._timestamps[key] = True
        return True  # Allowed
