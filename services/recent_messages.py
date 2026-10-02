"""Short-lived message history used for moderation cleanup."""
import logging
import time
from collections import deque

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from cachetools import TTLCache

from config import config

logger = logging.getLogger(__name__)

# (chat_id, user_id) -> deque[(monotonic timestamp, message_id)]
_recent_messages: TTLCache = TTLCache(
    maxsize=config.nsfw.recent_users_max,
    ttl=config.nsfw.recent_cleanup_seconds,
    timer=lambda: time.monotonic(),
)


def track_recent_message(chat_id: int, user_id: int, message_id: int) -> None:
    """Remember a message long enough for retrospective moderation."""
    key = (chat_id, user_id)
    history = _recent_messages.get(key)
    if history is None:
        history = deque(maxlen=config.nsfw.recent_messages_max)

    now = time.monotonic()
    cutoff = now - config.nsfw.recent_cleanup_seconds
    while history and history[0][0] < cutoff:
        history.popleft()
    history.append((now, message_id))
    # Refresh expiry on activity; inactive users expire as a whole.
    _recent_messages[key] = history


async def delete_recent_messages(
    bot, chat_id: int, user_id: int, *, exclude_message_id: int | None = None
) -> int:
    """Delete recent messages, retaining failed IDs for a later retry."""
    key = (chat_id, user_id)
    history = _recent_messages.get(key)
    if not history:
        return 0

    cutoff = time.monotonic() - config.nsfw.recent_cleanup_seconds
    message_ids = {
        message_id
        for timestamp, message_id in history
        if timestamp >= cutoff and message_id != exclude_message_id
    }
    if not message_ids:
        return 0

    removed_ids = set()
    deleted = 0
    ordered_ids = sorted(message_ids)
    for offset in range(0, len(ordered_ids), 100):
        batch = ordered_ids[offset:offset + 100]
        try:
            await bot.delete_messages(chat_id, batch)
            deleted += len(batch)
            removed_ids.update(batch)
        except TelegramBadRequest:
            # One undeletable message must not strand the rest of the batch
            for message_id in batch:
                try:
                    await bot.delete_message(chat_id, message_id)
                    deleted += 1
                    removed_ids.add(message_id)
                except TelegramBadRequest as exc:
                    if "message to delete not found" in str(exc).lower():
                        removed_ids.add(message_id)
                    else:
                        logger.exception("Failed to delete message %s in chat %s", message_id, chat_id)
                except TelegramAPIError:
                    logger.exception("Recent-message cleanup interrupted for user %s in chat %s", user_id, chat_id)
                    break
        except TelegramAPIError:
            logger.exception("Recent-message cleanup failed for user %s in chat %s", user_id, chat_id)
            break

    # Re-read after the API calls: messages can arrive while deletion awaits
    current = _recent_messages.get(key)
    if current is not None:
        remaining = deque(
            ((timestamp, mid) for timestamp, mid in current
             if timestamp >= cutoff and mid not in removed_ids and mid != exclude_message_id),
            maxlen=config.nsfw.recent_messages_max,
        )
        if remaining:
            _recent_messages[key] = remaining
        else:
            _recent_messages.pop(key, None)
    logger.info(
        "Deleted %s recent messages for user %s in chat %s after NSFW detection",
        deleted, user_id, chat_id,
    )
    return deleted


async def delete_message_if_present(message) -> None:
    """A queued update may refer to a message already removed by cleanup."""
    try:
        await message.delete()
    except TelegramBadRequest as exc:
        if "message to delete not found" not in str(exc).lower():
            raise


async def ban_and_cleanup(bot, chat_id: int, user_id: int) -> int:
    """Ban with server-side revocation, then clean tracked messages as well."""
    await bot.ban_chat_member(chat_id=chat_id, user_id=user_id, revoke_messages=True)
    
    # Role checks must not keep returning the pre-ban membership
    from services.cache import invalidate_tgmember_cache
    invalidate_tgmember_cache(chat_id, user_id)
    return await delete_recent_messages(bot, chat_id, user_id)


def clear_recent_messages() -> None:
    """Clear tracked history (primarily for tests)."""
    _recent_messages.clear()
