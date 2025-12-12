"""
Reports tracking service.

Tracks recent reports per group to avoid duplicates.
Manages reporter rewards when admins take action.
"""
from collections import deque
import logging

from config import config

logger = logging.getLogger(__name__)

# Track recent reported message IDs per group
# Key: group_id, Value: deque of reported message IDs
_recent_reports: dict[int, deque] = {}

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
