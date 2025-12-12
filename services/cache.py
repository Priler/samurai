"""
Cache service for member data, TG members, gender detection, and NSFW results.

Features:
- TTL-based caching (auto-expiry)
- Proper multi-group support (chat_id, user_id) keys
- Batch database updates for performance
- NSFW result caching
- Lightweight data storage (dicts instead of ORM objects)
- Configurable cache sizes via config.toml
"""
import asyncio
from dataclasses import dataclass
from functools import wraps
from typing import Optional

import ormar
from cachetools import TTLCache, LRUCache

from config import config
from db.models import Member
from services.gender import detect_gender as _detect_gender, Gender

# =============================================================================
# LIGHTWEIGHT MEMBER DATA
# =============================================================================

@dataclass
class MemberData:
    """Lightweight member data for caching (no ORM references)."""
    id: int
    user_id: int
    messages_count: int
    reputation_points: int
    violations_count_profanity: int
    violations_count_spam: int
    halloween_sweets: int
    halloween_golden_tickets: int
    
    @classmethod
    def from_orm(cls, member: Member) -> "MemberData":
        """Create from ORM object."""
        return cls(
            id=member.id,
            user_id=member.user_id,
            messages_count=member.messages_count,
            reputation_points=member.reputation_points,
            violations_count_profanity=member.violations_count_profanity,
            violations_count_spam=member.violations_count_spam,
            halloween_sweets=member.halloween_sweets,
            halloween_golden_tickets=member.halloween_golden_tickets,
        )


# =============================================================================
# CACHE INSTANCES (sizes from config)
# =============================================================================

# Member DB records
members_cache: TTLCache = TTLCache(
    maxsize=config.cache.members_maxsize, 
    ttl=config.cache.members_ttl
)

# Telegram member objects
# Key: (chat_id, user_id) tuple for multi-group support
tgmembers_cache: TTLCache = TTLCache(
    maxsize=config.cache.tgmembers_maxsize, 
    ttl=config.cache.tgmembers_ttl
)

# Gender detection (LRU, no TTL - names don't change)
gender_detections_cache: LRUCache = LRUCache(
    maxsize=config.cache.gender_maxsize
)

# NSFW detection results
# Key: (user_id, photo_file_unique_id) tuple
nsfw_results_cache: TTLCache = TTLCache(
    maxsize=config.cache.nsfw_maxsize, 
    ttl=config.cache.nsfw_ttl
)

# =============================================================================
# BATCH UPDATE SYSTEM
# =============================================================================

# Pending member updates: {user_id: {"field": delta_value}}
_pending_updates: dict[int, dict[str, int]] = {}
_batch_lock = asyncio.Lock()
_flush_task: Optional[asyncio.Task] = None


async def queue_member_update(user_id: int, **changes: int) -> None:
    """
    Queue member field updates for batch processing.
    
    Args:
        user_id: User ID to update
        **changes: Field deltas, e.g. messages_count=1, reputation_points=5
    """
    async with _batch_lock:
        if user_id not in _pending_updates:
            _pending_updates[user_id] = {}
        
        for field, delta in changes.items():
            current = _pending_updates[user_id].get(field, 0)
            _pending_updates[user_id][field] = current + delta


async def flush_member_updates() -> int:
    """
    Flush all pending member updates to database.
    
    Returns:
        Number of users updated
    """
    async with _batch_lock:
        if not _pending_updates:
            return 0
        
        updates_copy = dict(_pending_updates)
        _pending_updates.clear()
    
    count = 0
    for user_id, changes in updates_copy.items():
        try:
            member = await Member.objects.get(user_id=user_id)
            for field, delta in changes.items():
                current_value = getattr(member, field, 0)
                setattr(member, field, current_value + delta)
            await member.update()
            count += 1
            
            # Invalidate cache after update
            invalidate_member_cache(user_id)
        except ormar.NoMatch:
            pass
        except Exception:
            pass
    
    return count


async def _periodic_flush(interval: int) -> None:
    """Background task to flush updates periodically."""
    while True:
        await asyncio.sleep(interval)
        await flush_member_updates()


def start_batch_flush_task(interval: Optional[int] = None) -> asyncio.Task:
    """Start the background batch flush task."""
    global _flush_task
    if interval is None:
        interval = config.cache.batch_flush_interval
    if _flush_task is None or _flush_task.done():
        _flush_task = asyncio.create_task(_periodic_flush(interval))
    return _flush_task


def stop_batch_flush_task() -> None:
    """Stop the background batch flush task."""
    global _flush_task
    if _flush_task and not _flush_task.done():
        _flush_task.cancel()
        _flush_task = None


# =============================================================================
# GENDER DETECTION CACHE
# =============================================================================

def cache_gender_detection(func):
    """Decorator for caching gender detection results."""
    @wraps(func)
    def wrapper(name: str) -> Gender:
        if name in gender_detections_cache:
            return gender_detections_cache[name]

        result = func(name)
        gender_detections_cache[name] = result
        return result

    return wrapper


@cache_gender_detection
def detect_gender(name: str) -> Gender:
    """Detect gender with caching."""
    return _detect_gender(name)


# =============================================================================
# TELEGRAM MEMBER CACHE (Multi-group aware)
# =============================================================================

async def retrieve_tgmember(bot, chat_id: int, user_id: int):
    """
    Retrieve Telegram member with caching.
    
    Uses (chat_id, user_id) tuple as key to properly support
    multi-group scenarios where user may have different roles.
    """
    cache_key = (chat_id, user_id)
    
    if cache_key in tgmembers_cache:
        return tgmembers_cache[cache_key]
    
    result = await bot.get_chat_member(chat_id, user_id)
    tgmembers_cache[cache_key] = result
    return result


def invalidate_tgmember_cache(chat_id: int, user_id: int) -> None:
    """Invalidate TG member cache for specific user in specific chat."""
    cache_key = (chat_id, user_id)
    if cache_key in tgmembers_cache:
        del tgmembers_cache[cache_key]


def invalidate_tgmember_cache_all(user_id: int) -> None:
    """Invalidate TG member cache for user across all chats."""
    keys_to_delete = [k for k in tgmembers_cache.keys() if k[1] == user_id]
    for key in keys_to_delete:
        del tgmembers_cache[key]


# =============================================================================
# DATABASE MEMBER CACHE (stores lightweight dataclass, not ORM object)
# =============================================================================

async def retrieve_or_create_member(user_id: int) -> MemberData:
    """
    Retrieve or create member record with caching.
    
    Returns lightweight MemberData instead of ORM object to prevent
    memory leaks from cached ORM session references.
    """
    if user_id in members_cache:
        return members_cache[user_id]
    
    try:
        member = await Member.objects.get(user_id=user_id)
    except ormar.NoMatch:
        member = await Member.objects.create(user_id=user_id, messages_count=1)
    
    # Cache lightweight dataclass, not ORM object
    member_data = MemberData.from_orm(member)
    members_cache[user_id] = member_data
    return member_data


async def get_member_orm(user_id: int) -> Member:
    """
    Get actual ORM Member object for direct updates.
    
    Use this ONLY for admin commands that need to set absolute values.
    For delta updates (add/subtract), use queue_member_update() instead.
    
    Note: Does not use cache - always fetches fresh from DB.
    """
    try:
        return await Member.objects.get(user_id=user_id)
    except ormar.NoMatch:
        return await Member.objects.create(user_id=user_id, messages_count=1)


def invalidate_member_cache(user_id: int) -> None:
    """Invalidate member cache for specific user."""
    if user_id in members_cache:
        del members_cache[user_id]


def update_member_cache(user_id: int, member: Member) -> None:
    """Update member in cache with fresh data."""
    members_cache[user_id] = MemberData.from_orm(member)


# =============================================================================
# NSFW DETECTION CACHE
# =============================================================================

def get_cached_nsfw_result(user_id: int, photo_file_unique_id: str) -> Optional[bool]:
    """
    Get cached NSFW detection result.
    
    Returns:
        True/False if cached, None if not in cache
    """
    cache_key = (user_id, photo_file_unique_id)
    return nsfw_results_cache.get(cache_key)


def cache_nsfw_result(user_id: int, photo_file_unique_id: str, is_nsfw: bool) -> None:
    """Cache NSFW detection result."""
    cache_key = (user_id, photo_file_unique_id)
    nsfw_results_cache[cache_key] = is_nsfw


def invalidate_nsfw_cache(user_id: int) -> None:
    """Invalidate all NSFW cache entries for a user."""
    keys_to_delete = [k for k in nsfw_results_cache.keys() if k[0] == user_id]
    for key in keys_to_delete:
        del nsfw_results_cache[key]


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def is_trusted_user(member: MemberData) -> bool:
    """Check if user is trusted (has many messages)."""
    return member.messages_count >= config.cache.trusted_user_messages


def clear_all_caches() -> None:
    """Clear all caches (useful for testing)."""
    members_cache.clear()
    tgmembers_cache.clear()
    gender_detections_cache.clear()
    nsfw_results_cache.clear()
