"""
Managed chats + linked channels runtime registry.
"""
from __future__ import annotations

from datetime import datetime

import ormar
from cachetools import TTLCache

from config import config
from db.models import ManagedChat, LinkedChannel

_main_chats_cache: TTLCache = TTLCache(maxsize=1, ttl=60)
_linked_channels_cache: TTLCache = TTLCache(maxsize=1, ttl=60)


def _clear_cache() -> None:
    _main_chats_cache.clear()
    _linked_channels_cache.clear()


async def _first_or_none(queryset):
    try:
        return await queryset.first()
    except ormar.NoMatch:
        return None


async def bootstrap_chat_registry() -> None:
    """Seed DB from legacy config if empty."""
    existing_main = await ManagedChat.objects.filter(is_enabled=True).count()
    if existing_main == 0 and config.groups.main:
        now = datetime.now()
        for chat_id in config.groups.main:
            already = await _first_or_none(ManagedChat.objects.filter(chat_id=chat_id))
            if not already:
                await ManagedChat.objects.create(
                    chat_id=chat_id,
                    chat_type="supergroup",
                    title=None,
                    bot_status="administrator",
                    is_enabled=True,
                    updated_at=now
                )

    existing_linked = await LinkedChannel.objects.count()
    if existing_linked == 0 and config.groups.linked_channels:
        now = datetime.now()
        for channel_id in config.groups.linked_channels:
            await LinkedChannel.objects.create(
                group_chat_id=0,
                channel_chat_id=channel_id,
                source="legacy",
                updated_at=now
            )

    _clear_cache()


async def register_chat(
    chat_id: int,
    chat_type: str = "supergroup",
    title: str | None = None,
    bot_status: str = "administrator",
    is_enabled: bool = True
) -> None:
    row = await _first_or_none(ManagedChat.objects.filter(chat_id=chat_id))
    now = datetime.now()
    if row:
        row.chat_type = chat_type
        row.title = title
        row.bot_status = bot_status
        row.is_enabled = is_enabled
        row.updated_at = now
        await row.update()
    else:
        await ManagedChat.objects.create(
            chat_id=chat_id,
            chat_type=chat_type,
            title=title,
            bot_status=bot_status,
            is_enabled=is_enabled,
            updated_at=now
        )
    _clear_cache()


async def disable_chat(chat_id: int) -> bool:
    row = await _first_or_none(ManagedChat.objects.filter(chat_id=chat_id))
    if not row:
        return False
    row.is_enabled = False
    row.updated_at = datetime.now()
    await row.update()
    _clear_cache()
    return True


async def list_managed_chats(enabled_only: bool = True) -> list[ManagedChat]:
    if enabled_only:
        return await ManagedChat.objects.filter(is_enabled=True).order_by("chat_id").all()
    return await ManagedChat.objects.order_by("chat_id").all()


async def get_main_chat_ids() -> list[int]:
    if "main" in _main_chats_cache:
        return list(_main_chats_cache["main"])

    rows = await ManagedChat.objects.filter(is_enabled=True).all()
    if rows:
        chat_ids = sorted({row.chat_id for row in rows})
    else:
        chat_ids = sorted(set(config.groups.main))
    _main_chats_cache["main"] = chat_ids
    return chat_ids


async def is_main_chat(chat_id: int) -> bool:
    return chat_id in set(await get_main_chat_ids())


async def add_linked_channel(group_chat_id: int, channel_chat_id: int, source: str = "manual") -> None:
    existing = await _first_or_none(LinkedChannel.objects.filter(
        group_chat_id=group_chat_id,
        channel_chat_id=channel_chat_id
    ))
    if existing:
        existing.source = source
        existing.updated_at = datetime.now()
        await existing.update()
    else:
        await LinkedChannel.objects.create(
            group_chat_id=group_chat_id,
            channel_chat_id=channel_chat_id,
            source=source,
            updated_at=datetime.now()
        )
    _clear_cache()


async def remove_linked_channel(group_chat_id: int, channel_chat_id: int) -> bool:
    row = await _first_or_none(LinkedChannel.objects.filter(
        group_chat_id=group_chat_id,
        channel_chat_id=channel_chat_id
    ))
    if not row:
        return False
    await row.delete()
    _clear_cache()
    return True


async def list_linked_channels(group_chat_id: int | None = None) -> list[LinkedChannel]:
    if group_chat_id is None:
        return await LinkedChannel.objects.order_by("group_chat_id").all()
    return await LinkedChannel.objects.filter(group_chat_id=group_chat_id).all()


async def get_linked_channel_ids() -> set[int]:
    if "linked" in _linked_channels_cache:
        return set(_linked_channels_cache["linked"])

    rows = await LinkedChannel.objects.all()
    if rows:
        ids = {row.channel_chat_id for row in rows}
    else:
        ids = set(config.groups.linked_channels)
    _linked_channels_cache["linked"] = list(ids)
    return ids


async def is_linked_channel(channel_chat_id: int) -> bool:
    return channel_chat_id in await get_linked_channel_ids()
