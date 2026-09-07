"""
Coordinated newcomer-burst detection.
"""
import logging
import time
from collections import deque

from config import config

logger = logging.getLogger(__name__)

# chat_id -> deque[(monotonic timestamp, user_id)]
_recent_newcomers: dict[int, deque[tuple[float, int]]] = {}

# chat_id -> monotonic timestamp of the last burst alert, to avoid log spam
_last_alert: dict[int, float] = {}


_records_seen = 0


def _prune(history: deque, cutoff: float) -> None:
    while history and history[0][0] < cutoff:
        history.popleft()


def _maybe_sweep() -> None:
    """Drop idle chats every so often so the tracker cannot grow unbounded."""
    global _records_seen
    _records_seen += 1
    if _records_seen % 500:
        return
    removed = sweep()
    if removed:
        logger.debug("Burst tracker swept %s idle chats", removed)


def record_newcomer(chat_id: int, user_id: int) -> int:
    """Record a message from a low-rep account and return the cohort size.

    Returns the number of distinct low-rep accounts that have spoken in this
    chat within the configured window, including this one.
    """
    window = config.spam.burst_window_seconds
    now = time.monotonic()

    history = _recent_newcomers.get(chat_id)
    if history is None:
        history = deque(maxlen=config.spam.burst_max_tracked)
        _recent_newcomers[chat_id] = history

    _prune(history, now - window)
    history.append((now, user_id))

    _maybe_sweep()

    return len({uid for _, uid in history})


def is_burst(cohort_size: int) -> bool:
    """Check whether a cohort size crosses the burst threshold."""
    return (
        config.spam.burst_enabled
        and cohort_size >= config.spam.burst_min_accounts
    )


def should_alert(chat_id: int) -> bool:
    """Rate-limit burst alerts so one wave produces a manageable log volume."""
    now = time.monotonic()
    last = _last_alert.get(chat_id, 0.0)
    if now - last < config.spam.burst_alert_cooldown:
        return False
    _last_alert[chat_id] = now
    return True


def sweep(max_idle: int = 3600) -> int:
    """Drop chats with no recent activity. Returns the number removed."""
    cutoff = time.monotonic() - max_idle
    stale = [
        chat_id for chat_id, history in _recent_newcomers.items()
        if not history or history[-1][0] < cutoff
    ]
    for chat_id in stale:
        del _recent_newcomers[chat_id]
        _last_alert.pop(chat_id, None)
    return len(stale)


def clear() -> None:
    """Clear tracked state (primarily for tests)."""
    _recent_newcomers.clear()
    _last_alert.clear()
