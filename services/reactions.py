"""Reputation-based reaction permissions for configured discussion supergroups."""
import asyncio
import logging
import time
from contextlib import suppress
from datetime import datetime
from weakref import WeakValueDictionary

from aiogram.exceptions import TelegramRetryAfter, TelegramBadRequest, TelegramForbiddenError
from aiogram.types import ChatPermissions
from cachetools import TTLCache

from config import config
from db.database import ormar_config
from db.models import Member, ReactionRestriction
from services.cache import retrieve_or_create_member, invalidate_tgmember_cache
from utils.enums import MemberStatus

logger = logging.getLogger(__name__)
_locks: WeakValueDictionary = WeakValueDictionary()
_bot = None
_task: asyncio.Task | None = None
_changed = asyncio.Event()
_dirty_users: set[int] = set()
_rescan = False
_retry_until = 0.0
_synced: TTLCache = TTLCache(maxsize=10000, ttl=30)


def _lock(chat_id: int, user_id: int) -> asyncio.Lock:
    key = (chat_id, user_id)
    lock = _locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _locks[key] = lock
    return lock


def notify_reputation_change(user_id: int) -> None:
    """Coalesce updates from messages, reports and owner commands."""
    global _rescan
    if _bot is None or not config.reactions.enabled:
        return
    if len(_dirty_users) < 10000:
        _dirty_users.add(user_id)
    else:
        _rescan = True
    _changed.set()


def is_running() -> bool:
    return _bot is not None


async def _sync_member(bot, chat_id: int, user_id: int) -> bool:
    """Caller holds the member lock. Return whether policy disallows reactions."""
    role = await bot.get_chat_member(chat_id, user_id)
    if role.status in MemberStatus.admin_statuses():
        return False
    if role.status not in ("member", "restricted") or (
        role.status == "restricted" and not role.is_member
    ):
        await ReactionRestriction.objects.filter(chat_id=chat_id, user_id=user_id).delete()
        return False
    if role.user.is_bot:
        return False

    member = await retrieve_or_create_member(user_id)
    blocked = config.reactions.enabled and member.reputation_points < config.reactions.rep_threshold
    owned = await ReactionRestriction.objects.get_or_none(chat_id=chat_id, user_id=user_id)
    if not blocked and owned is None:
        return False
    if blocked and role.status == "restricted":
        current = role.can_react_to_messages
        if current is None:
            current = role.can_send_messages
        if not current:
            return True

    chat = await bot.get_chat(chat_id)
    if chat.type != "supergroup":
        return False
    defaults = chat.permissions
    if defaults is None:
        raise ValueError(f"Missing default permissions for supergroup {chat_id}")
    source = role if role.status == "restricted" else defaults
    permissions = {name: bool(getattr(source, name, False)) for name in ChatPermissions.model_fields}
    for name in ("can_edit_tag", "can_manage_topics"):
        if getattr(source, name, None) is None:
            permissions[name] = permissions["can_pin_messages"]
    # Telegram's omitted reaction flag inherits can_send_messages.
    current = getattr(source, "can_react_to_messages", None)
    if current is None:
        current = permissions["can_send_messages"]
    permissions["can_react_to_messages"] = current
    until_date = role.until_date if role.status == "restricted" else 0
    until_timestamp = until_date.timestamp() if isinstance(until_date, datetime) else until_date
    if until_timestamp and until_timestamp - time.time() < 30:
        # Telegram treats deadlines less than 30s away as permanent. Let the
        # existing restriction expire rather than accidentally extending a mute.
        return blocked

    created = False
    if blocked:
        if not current:
            return True  # Existing manual restrictions are not ours to lift.
        if owned is None:
            owned = await ReactionRestriction.objects.create(chat_id=chat_id, user_id=user_id)
            created = True
        permissions["can_react_to_messages"] = False
    else:
        if current or role.status == "member":
            await owned.delete()
            return False
        # Leave active mutes in place; reconcile again after they expire.
        if not permissions["can_send_messages"]:
            return False
        allowed = defaults.can_react_to_messages
        if allowed is None:
            allowed = defaults.can_send_messages
        if not allowed:
            await owned.delete()
            return False
        permissions["can_react_to_messages"] = True

    try:
        await bot.restrict_chat_member(
            chat_id=chat_id, user_id=user_id,
            permissions=ChatPermissions(**permissions),
            use_independent_chat_permissions=True, until_date=until_date,
        )
    except (TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter):
        if created:
            await owned.delete()  # A rejected API call did not impose a restriction.
        raise
    invalidate_tgmember_cache(chat_id, user_id)
    if not blocked:
        await owned.delete()
    logger.info("Reaction permission %s for user %s in chat %s (reputation %s)",
                "disabled" if blocked else "restored", user_id, chat_id, member.reputation_points)
    return blocked


async def sync_member(bot, chat_id: int, user_id: int, *, force: bool = False) -> bool:
    """Synchronize one member without interrupting other moderation on API failures."""
    global _retry_until
    if not config.groups.is_main_group(chat_id):
        return False
    if time.monotonic() < _retry_until:
        return False
    async with _lock(chat_id, user_id):
        try:
            member = await retrieve_or_create_member(user_id)
            signature = (config.reactions.enabled, config.reactions.rep_threshold,
                         member.reputation_points < config.reactions.rep_threshold)
            previous = _synced.get((chat_id, user_id))
            if not force and previous is not None and previous[0] == signature:
                return previous[1]
            result = await _sync_member(bot, chat_id, user_id)
            _synced[(chat_id, user_id)] = (signature, result)
            return result
        except TelegramRetryAfter as exc:
            _retry_until = time.monotonic() + exc.retry_after
            notify_reputation_change(user_id)
            logger.warning("Reaction permissions rate limited for %s seconds", exc.retry_after)
        except Exception:
            logger.exception("Failed to synchronize reactions for user %s in chat %s", user_id, chat_id)
    return False


async def restrict_member(bot, **kwargs):
    """Serialize moderator mutes with policy changes to avoid overwriting a mute."""
    chat_id, user_id = kwargs["chat_id"], kwargs["user_id"]
    async with _lock(chat_id, user_id):
        result = await bot.restrict_chat_member(**kwargs)
        invalidate_tgmember_cache(chat_id, user_id)
        _synced.pop((chat_id, user_id), None)
    notify_reputation_change(user_id)
    return result


async def ban_member(bot, **kwargs):
    """A reaction permission write must finish before a concurrent bot ban."""
    chat_id, user_id = kwargs["chat_id"], kwargs["user_id"]
    async with _lock(chat_id, user_id):
        result = await bot.ban_chat_member(**kwargs)
        invalidate_tgmember_cache(chat_id, user_id)
        _synced.pop((chat_id, user_id), None)
    notify_reputation_change(user_id)
    return result


async def reconcile_known_members(bot) -> None:
    """Page existing reputation records; no assumption that every user is in every chat."""
    cursor = 0
    source = Member if config.reactions.enabled else ReactionRestriction
    while True:
        members = await source.objects.filter(id__gt=cursor).order_by("id").limit(100).all()
        if not members:
            break
        for member in members:
            for chat_id in config.groups.main:
                await _wait_for_rate_limit()
                await sync_member(bot, chat_id, member.user_id, force=True)
                await asyncio.sleep(0.1)
        cursor = members[-1].id


async def _wait_for_rate_limit() -> None:
    delay = _retry_until - time.monotonic()
    if delay > 0:
        await asyncio.sleep(delay)


async def _run(bot) -> None:
    global _rescan
    next_scan = 0.0
    while True:
        try:
            if _rescan or time.monotonic() >= next_scan:
                _rescan = False
                await reconcile_known_members(bot)
                next_scan = time.monotonic() + 300
            while _dirty_users:
                user_id = _dirty_users.pop()
                for chat_id in config.groups.main:
                    await _wait_for_rate_limit()
                    await sync_member(bot, chat_id, user_id)
                    await asyncio.sleep(0.1)
        except Exception:
            logger.exception("Reaction permission reconciliation failed; retrying later")
            next_scan = time.monotonic() + 30
        _changed.clear()
        try:
            await asyncio.wait_for(_changed.wait(), timeout=max(0.1, next_scan - time.monotonic()))
        except asyncio.TimeoutError:
            pass


async def start(bot) -> None:
    """Create only the additive policy table and start background reconciliation."""
    global _bot, _task, _changed
    if _task is not None and not _task.done():
        return
    async with ormar_config.engine.begin() as connection:
        await connection.run_sync(ReactionRestriction.ormar_config.table.create, checkfirst=True)
    _bot = bot
    _changed = asyncio.Event()
    _task = asyncio.create_task(_run(bot))


async def stop() -> None:
    global _bot, _task
    _bot = None
    if _task is not None:
        _task.cancel()
        with suppress(asyncio.CancelledError):
            await _task
    _task = None
    _dirty_users.clear()
    _synced.clear()
