"""
Filter to check if message is from one of the main groups.
"""
from aiogram.filters import Filter
from aiogram.types import Message, CallbackQuery

from config import config


class InMainGroups(Filter):
    """
    Filter that passes if chat_id is in the configured main groups.
    
    Uses O(1) set lookup for performance.
    
    Usage:
        @router.message(InMainGroups())
        async def handler(message: Message):
            ...
    """
    
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        if isinstance(event, CallbackQuery):
            if not event.message:
                return False
            chat_id = event.message.chat.id
        else:
            chat_id = event.chat.id
        
        print(chat_id)
        # Use O(1) set lookup instead of O(n) list lookup
        return config.groups.is_main_group(chat_id)
