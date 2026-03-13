"""
Per-user per-chat message interval limiter.
"""
from __future__ import annotations

import time
from cachetools import TTLCache

# key -> last message timestamp
_timestamps: TTLCache = TTLCache(maxsize=200000, ttl=24 * 3600)


def check_message_interval(chat_id: int, user_id: int, min_interval_sec: int) -> tuple[bool, int]:
    """
    Check and update message interval.

    Returns:
        (is_allowed, remaining_seconds)
    """
    if min_interval_sec <= 0:
        return True, 0

    key = (chat_id, user_id)
    now = time.time()
    last = _timestamps.get(key, 0.0)
    delta = now - last
    if delta < min_interval_sec:
        remaining = int(min_interval_sec - delta + 0.999)
        return False, max(remaining, 1)

    _timestamps[key] = now
    return True, 0
