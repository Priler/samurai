"""
Reports tracking service.

Tracks recent reports per group to avoid duplicates.
Manages reporter rewards when admins take action.
"""
from collections import deque
import asyncio
import logging
from cachetools import TTLCache

from config import config

logger = logging.getLogger(__name__)

# Track recent reported message IDs per group
# Key: group_id, Value: deque of reported message IDs
_recent_reports: dict[int, deque] = {}
_state_lock = asyncio.Lock()
_pending_reports: set[tuple[int, int]] = set()
_processing_report_actions: set[tuple[int, int]] = set()
_resolved_reports: TTLCache = TTLCache(maxsize=5000, ttl=86400)
_active_report_by_user: TTLCache = TTLCache(maxsize=5000, ttl=86400)
_report_users: TTLCache = TTLCache(maxsize=5000, ttl=86400)

# Max reports to track per group
MAX_TRACKED_REPORTS = 20


def is_already_reported(group_id: int, message_id: int) -> bool:
    """Check if a message has already been reported recently."""
    if group_id not in _recent_reports:
        return False
    return message_id in _recent_reports[group_id]


def track_report(group_id: int, message_id: int) -> None:
    """Track a new report."""
    if group_id not in _recent_reports:
        _recent_reports[group_id] = deque(maxlen=MAX_TRACKED_REPORTS)
    
    _recent_reports[group_id].append(message_id)
    logger.debug(f"Tracked report: group={group_id}, msg={message_id}")


async def begin_report(group_id: int, message_id: int, reported_user_id: int) -> bool:
    """Atomically reserve a report while it is delivered to moderators."""
    key = (group_id, message_id)
    async with _state_lock:
        if (
            key in _pending_reports
            or is_already_reported(group_id, message_id)
            or reported_user_id in _active_report_by_user
        ):
            return False
        _pending_reports.add(key)
        _active_report_by_user[reported_user_id] = key
        _report_users[key] = reported_user_id
        return True


async def finish_report(group_id: int, message_id: int, success: bool) -> None:
    """Commit or roll back a report reservation."""
    key = (group_id, message_id)
    async with _state_lock:
        _pending_reports.discard(key)
        if success:
            track_report(group_id, message_id)
        else:
            user_id = _report_users.pop(key, None)
            if user_id is not None and _active_report_by_user.get(user_id) == key:
                _active_report_by_user.pop(user_id, None)


async def claim_report_action(group_id: int, message_id: int) -> bool:
    """Reserve an action until it succeeds or is released for retry."""
    key = (group_id, message_id)
    async with _state_lock:
        if key in _resolved_reports or key in _processing_report_actions:
            return False
        _processing_report_actions.add(key)
        return True


async def finish_report_action(group_id: int, message_id: int, success: bool) -> None:
    """Commit successful moderation; failed actions remain retryable."""
    key = (group_id, message_id)
    async with _state_lock:
        _processing_report_actions.discard(key)
        if not success:
            return
        _resolved_reports[key] = True
        user_id = _report_users.pop(key, None)
        if user_id is not None and _active_report_by_user.get(user_id) == key:
            _active_report_by_user.pop(user_id, None)
        remove_report(group_id, message_id)


def remove_report(group_id: int, message_id: int) -> None:
    """Remove a report from tracking (e.g., when message is deleted)."""
    if group_id not in _recent_reports:
        return
    
    try:
        _recent_reports[group_id].remove(message_id)
        logger.debug(f"Removed report: group={group_id}, msg={message_id}")
    except ValueError:
        pass  # Not in deque


def get_report_count(group_id: int) -> int:
    """Get count of tracked reports for a group."""
    if group_id not in _recent_reports:
        return 0
    return len(_recent_reports[group_id])


def clear_group_reports(group_id: int) -> None:
    """Clear all tracked reports for a group."""
    if group_id in _recent_reports:
        _recent_reports[group_id].clear()
