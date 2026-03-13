"""
Owner management service with DB-backed multi-owner support.
"""
from __future__ import annotations

from datetime import datetime

import ormar
from cachetools import TTLCache

from config import config
from db.models import BotOwner

_owners_cache: TTLCache = TTLCache(maxsize=1, ttl=60)


async def _first_or_none(queryset):
    try:
        return await queryset.first()
    except ormar.NoMatch:
        return None


async def bootstrap_owners() -> None:
    """Ensure at least one owner exists (from legacy config)."""
    active_count = await BotOwner.objects.filter(is_active=True).count()
    if active_count == 0 and config.bot.owner:
        await BotOwner.objects.create(
            user_id=config.bot.owner,
            is_active=True,
            added_by=None,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
    _owners_cache.clear()


async def list_owner_ids() -> list[int]:
    if "ids" in _owners_cache:
        return list(_owners_cache["ids"])
    rows = await BotOwner.objects.filter(is_active=True).all()
    ids = sorted({row.user_id for row in rows})
    if not ids and config.bot.owner:
        ids = [config.bot.owner]
    _owners_cache["ids"] = ids
    return ids


async def is_owner(user_id: int) -> bool:
    return user_id in await list_owner_ids()


async def add_owner(user_id: int, actor_id: int | None = None) -> bool:
    existing = await _first_or_none(BotOwner.objects.filter(user_id=user_id))
    now = datetime.now()
    if existing:
        if existing.is_active:
            return False
        existing.is_active = True
        existing.updated_at = now
        existing.added_by = actor_id
        await existing.update()
    else:
        await BotOwner.objects.create(
            user_id=user_id,
            is_active=True,
            added_by=actor_id,
            created_at=now,
            updated_at=now
        )
    _owners_cache.clear()
    return True


async def remove_owner(user_id: int) -> bool:
    row = await _first_or_none(BotOwner.objects.filter(user_id=user_id, is_active=True))
    if not row:
        return False

    active_count = await BotOwner.objects.filter(is_active=True).count()
    if active_count <= 1:
        raise ValueError("Cannot remove the last owner")

    row.is_active = False
    row.updated_at = datetime.now()
    await row.update()
    _owners_cache.clear()
    return True
