"""
Internationalization middleware.

Injects i18n helper function into handler context,
allowing handlers to use translations with user's preferred locale.
"""
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

from core.i18n import get_i18n


class I18nMiddleware(BaseMiddleware):
    """
    Middleware that injects i18n function into handler data.
    
    Usage in handlers:
        async def handler(message: Message, i18n: Callable) -> None:
            text = i18n("error-no-reply")
            await message.reply(text)
    
    Or with the _ function directly:
        from core.i18n import _
        text = _("error-no-reply")
    """
    
    def __init__(self, default_locale: str = "ru") -> None:
        """
        Initialize middleware.
        
        Args:
            default_locale: Default locale if user's locale is not available
        """
        self.default_locale = default_locale
        super().__init__()
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """Process event and inject i18n."""
        # Get user from event
        user: User | None = data.get("event_from_user")
        
        # Determine locale
        locale = self.default_locale
        if user and user.language_code:
            i18n = get_i18n()
            if user.language_code in i18n.available_locales:
                locale = user.language_code
            elif user.language_code[:2] in i18n.available_locales:
                # Try base language (e.g., "en-US" -> "en")
                locale = user.language_code[:2]
        
        # Create bound translation function
        i18n = get_i18n()
        
        def translate(key: str, **kwargs: Any) -> str:
            return i18n.get(key, locale=locale, **kwargs)
        
        # Inject into handler data
        data["i18n"] = translate
        data["locale"] = locale
        
        return await handler(event, data)
