"""
Middlewares for the bot.
"""
from aiogram import Dispatcher

from .i18n import I18nMiddleware
from .throttling import ThrottlingMiddleware


def register_all_middlewares(
    dp: Dispatcher,
    default_locale: str = "ru",
    enable_throttling: bool = True,
    throttle_rate: float = 0.5,
    throttle_max_messages: int = 20,
    throttle_time_window: int = 60
) -> None:
    """
    Register all middlewares with the dispatcher.
    
    Args:
        dp: Dispatcher instance
        default_locale: Default locale for i18n
        enable_throttling: Enable rate limiting for private chats
        throttle_rate: Minimum seconds between messages
        throttle_max_messages: Max messages in time window
        throttle_time_window: Time window in seconds
    """
    # I18n middleware - adds i18n function to handler data
    i18n_middleware = I18nMiddleware(default_locale=default_locale)
    dp.message.middleware(i18n_middleware)
    dp.callback_query.middleware(i18n_middleware)
    dp.edited_message.middleware(i18n_middleware)
    
    # Throttling middleware - rate limiting for private chats
    if enable_throttling:
        throttle_middleware = ThrottlingMiddleware(
            rate_limit=throttle_rate,
            max_messages=throttle_max_messages,
            time_window=throttle_time_window
        )
        dp.message.middleware(throttle_middleware)


__all__ = [
    "register_all_middlewares",
    "I18nMiddleware",
    "ThrottlingMiddleware",
]
