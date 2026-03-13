"""
Filter to check if message is from one of the main groups.
"""
from aiogram.filters import Filter
from aiogram.types import Message, CallbackQuery

from services.chat_registry import is_main_chat


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
        
        return await is_main_chat(chat_id)
