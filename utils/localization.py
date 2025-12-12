"""
Localization module - re-exports from core.i18n.

This module provides backwards compatibility with the old
get_string() function while using the new Fluent-based i18n system.

For new code, prefer using:
    from core.i18n import _
    text = _("error-no-reply")

Or with the i18n middleware in handlers:
    async def handler(message: Message, i18n: Callable) -> None:
        text = i18n("error-no-reply")
"""
from core.i18n import get_string, _, _random, get_i18n

__all__ = ["get_string", "_", "_random", "get_i18n"]
