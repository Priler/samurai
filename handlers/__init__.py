"""
Handler registration for the bot.
"""
from aiogram import Dispatcher

from . import exceptions
from . import admin_actions
from . import user_actions
from . import callbacks
from . import personal_actions
from . import group_events


def register_all_handlers(dp: Dispatcher) -> None:
    """Register all routers with the dispatcher."""
    # Error handler should be first
    dp.include_router(exceptions.router)
    
    # Admin actions
    dp.include_router(admin_actions.router)
    
    # User actions (report, @admin)
    dp.include_router(user_actions.router)
    
    # Callback handlers
    dp.include_router(callbacks.router)
    
    # Personal/owner actions (ping, profanity check)
    dp.include_router(personal_actions.router)
    
    # Group events (main message processing) - should be last
    dp.include_router(group_events.router)


__all__ = ["register_all_handlers"]
