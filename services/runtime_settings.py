"""
Runtime settings service.

Provides:
- global + per-chat settings with precedence
- value validation/parsing
- in-memory TTL cache
- audit log on changes
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import ormar
from cachetools import TTLCache

from config import config
from db.models import BotSetting, ChatSetting, SettingsAuditLog


@dataclass(frozen=True)
class SettingDef:
    value_type: str
    min_value: float | None = None
    max_value: float | None = None
    per_chat: bool = True


SETTINGS_SCHEMA: dict[str, SettingDef] = {
    # groups/channels
    "groups.reports": SettingDef("int", per_chat=False),
    "groups.logs": SettingDef("int", per_chat=False),
    # moderation runtime
    "groups.new_users_nomedia": SettingDef("int", min_value=0),
    "moderation.new_user_automute_enabled": SettingDef("bool"),
    "moderation.new_user_automute_seconds": SettingDef("int", min_value=0),
    "moderation.message_min_interval_sec": SettingDef("int", min_value=0),
    "moderation.interval_violation_action": SettingDef("str"),
    "moderation.interval_penalty_points": SettingDef("int", min_value=0),
    "moderation.profanity_temp_ban_enabled": SettingDef("bool"),
    "moderation.profanity_temp_ban_seconds": SettingDef("int", min_value=0),
    # spam
    "spam.member_messages_threshold": SettingDef("int", min_value=0),
    "spam.member_reputation_threshold": SettingDef("int", min_value=-999999),
    "spam.allow_media_threshold": SettingDef("int", min_value=-999999),
    "spam.remove_first_comments_interval": SettingDef("int", min_value=0),
    "spam.allow_comments_rep_threshold": SettingDef("int", min_value=-999999),
    "spam.allow_comments_rep_threshold__woman": SettingDef("int", min_value=-999999),
    "spam.single_emoji_rep_threshold": SettingDef("int", min_value=-999999),
    "spam.links_rep_threshold": SettingDef("int", min_value=-999999),
    "spam.external_reply_rep_threshold": SettingDef("int", min_value=-999999),
    "spam.allow_forwards_threshold": SettingDef("int", min_value=-999999),
    "spam.forward_violation_penalty": SettingDef("int", min_value=0),
    "spam.autoban_enabled": SettingDef("bool"),
    "spam.autoban_threshold": SettingDef("int", min_value=1),
    "spam.autoban_rep_threshold": SettingDef("int", min_value=-999999),
    # nsfw
    "nsfw.enabled": SettingDef("bool"),
    "nsfw.check_rep_threshold": SettingDef("int", min_value=-999999),
    "nsfw.profile_check_cooldown": SettingDef("int", min_value=0),
    "nsfw.comb_sensual_prediction_threshold": SettingDef("float", min_value=0, max_value=1),
    "nsfw.comb_pornography_prediction_threshold": SettingDef("float", min_value=0, max_value=1),
    "nsfw.sensual_prediction_threshold": SettingDef("float", min_value=0, max_value=1),
    "nsfw.pornography_prediction_threshold": SettingDef("float", min_value=0, max_value=1),
    "nsfw.hentai_prediction_threshold": SettingDef("float", min_value=0, max_value=1),
    "nsfw.normal_prediction_threshold": SettingDef("float", min_value=0, max_value=1),
    "nsfw.normal_comb_sensual_prediction_threshold": SettingDef("float", min_value=0, max_value=1),
    "nsfw.normal_comb_pornography_prediction_threshold": SettingDef("float", min_value=0, max_value=1),
    "nsfw.anime_prediction_threshold": SettingDef("float", min_value=0, max_value=1),
    # throttling (PM legacy + general runtime)
    "throttling.enabled": SettingDef("bool", per_chat=False),
    "throttling.rate_limit": SettingDef("float", min_value=0, per_chat=False),
    "throttling.max_messages": SettingDef("int", min_value=1, per_chat=False),
    "throttling.time_window": SettingDef("int", min_value=1, per_chat=False),
}

DEFAULTS: dict[str, Any] = {
    "groups.reports": config.groups.reports,
    "groups.logs": config.groups.logs,
    "groups.new_users_nomedia": config.groups.new_users_nomedia,
    "moderation.new_user_automute_enabled": False,
    "moderation.new_user_automute_seconds": 0,
    "moderation.message_min_interval_sec": 0,
    "moderation.interval_violation_action": "delete",
    "moderation.interval_penalty_points": 0,
    "moderation.profanity_temp_ban_enabled": False,
    "moderation.profanity_temp_ban_seconds": 300,
    "spam.member_messages_threshold": config.spam.member_messages_threshold,
    "spam.member_reputation_threshold": config.spam.member_reputation_threshold,
    "spam.allow_media_threshold": config.spam.allow_media_threshold,
    "spam.remove_first_comments_interval": config.spam.remove_first_comments_interval,
    "spam.allow_comments_rep_threshold": config.spam.allow_comments_rep_threshold,
    "spam.allow_comments_rep_threshold__woman": config.spam.allow_comments_rep_threshold__woman,
    "spam.single_emoji_rep_threshold": config.spam.single_emoji_rep_threshold,
    "spam.links_rep_threshold": config.spam.links_rep_threshold,
    "spam.external_reply_rep_threshold": config.spam.external_reply_rep_threshold,
    "spam.allow_forwards_threshold": config.spam.allow_forwards_threshold,
    "spam.forward_violation_penalty": config.spam.forward_violation_penalty,
    "spam.autoban_enabled": config.spam.autoban_enabled,
    "spam.autoban_threshold": config.spam.autoban_threshold,
    "spam.autoban_rep_threshold": config.spam.autoban_rep_threshold,
    "nsfw.enabled": config.nsfw.enabled,
    "nsfw.check_rep_threshold": config.nsfw.check_rep_threshold,
    "nsfw.profile_check_cooldown": config.nsfw.profile_check_cooldown,
    "nsfw.comb_sensual_prediction_threshold": config.nsfw.comb_sensual_prediction_threshold,
    "nsfw.comb_pornography_prediction_threshold": config.nsfw.comb_pornography_prediction_threshold,
    "nsfw.sensual_prediction_threshold": config.nsfw.sensual_prediction_threshold,
    "nsfw.pornography_prediction_threshold": config.nsfw.pornography_prediction_threshold,
    "nsfw.hentai_prediction_threshold": config.nsfw.hentai_prediction_threshold,
    "nsfw.normal_prediction_threshold": config.nsfw.normal_prediction_threshold,
    "nsfw.normal_comb_sensual_prediction_threshold": config.nsfw.normal_comb_sensual_prediction_threshold,
    "nsfw.normal_comb_pornography_prediction_threshold": config.nsfw.normal_comb_pornography_prediction_threshold,
    "nsfw.anime_prediction_threshold": config.nsfw.anime_prediction_threshold,
    "throttling.enabled": config.throttling.enabled,
    "throttling.rate_limit": config.throttling.rate_limit,
    "throttling.max_messages": config.throttling.max_messages,
    "throttling.time_window": config.throttling.time_window,
}

_global_cache: TTLCache = TTLCache(maxsize=2048, ttl=120)
_chat_cache: TTLCache = TTLCache(maxsize=10000, ttl=120)


async def _first_or_none(queryset):
    try:
        return await queryset.first()
    except ormar.NoMatch:
        return None


def _serialize(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True)


def _deserialize(raw: str, value_type: str) -> Any:
    if value_type == "int":
        return int(raw)
    if value_type == "float":
        return float(raw)
    if value_type == "bool":
        return raw.lower() in ("1", "true", "yes", "on")
    if value_type == "list":
        return json.loads(raw)
    return raw


def _validate_value(key: str, value: Any) -> Any:
    if key not in SETTINGS_SCHEMA:
        raise ValueError(f"Unknown setting key: {key}")

    definition = SETTINGS_SCHEMA[key]
    expected = definition.value_type

    if expected == "int":
        value = int(value)
    elif expected == "float":
        value = float(value)
    elif expected == "bool":
        if isinstance(value, bool):
            pass
        elif isinstance(value, str):
            value = value.lower() in ("1", "true", "yes", "on")
        else:
            value = bool(value)
    elif expected == "list":
        if not isinstance(value, list):
            raise ValueError(f"{key} expects list")
    else:
        value = str(value)

    if isinstance(value, (int, float)):
        if definition.min_value is not None and value < definition.min_value:
            raise ValueError(f"{key} must be >= {definition.min_value}")
        if definition.max_value is not None and value > definition.max_value:
            raise ValueError(f"{key} must be <= {definition.max_value}")

    if key == "moderation.interval_violation_action":
        if value not in ("delete", "warn", "penalty"):
            raise ValueError(f"{key} must be one of: delete, warn, penalty")

    return value


def parse_setting_input(key: str, raw: str) -> Any:
    if key not in SETTINGS_SCHEMA:
        raise ValueError(f"Unknown setting key: {key}")
    definition = SETTINGS_SCHEMA[key]
    if definition.value_type == "bool":
        return _validate_value(key, raw)
    if definition.value_type == "int":
        return _validate_value(key, int(raw))
    if definition.value_type == "float":
        return _validate_value(key, float(raw))
    if definition.value_type == "list":
        return _validate_value(key, json.loads(raw))
    return _validate_value(key, raw)


def list_setting_keys() -> list[str]:
    return sorted(SETTINGS_SCHEMA.keys())


async def get_setting(key: str, chat_id: int | None = None) -> Any:
    if key not in SETTINGS_SCHEMA:
        raise ValueError(f"Unknown setting key: {key}")

    if chat_id is not None:
        cache_key = (chat_id, key)
        if cache_key in _chat_cache:
            return _chat_cache[cache_key]

        chat_row = await _first_or_none(ChatSetting.objects.filter(chat_id=chat_id, key=key))
        if chat_row:
            value = _deserialize(chat_row.value, chat_row.value_type)
            _chat_cache[cache_key] = value
            return value

    if key in _global_cache:
        return _global_cache[key]

    row = await _first_or_none(BotSetting.objects.filter(key=key))
    if row:
        value = _deserialize(row.value, row.value_type)
        _global_cache[key] = value
        return value

    return DEFAULTS[key]


async def set_setting(
    key: str,
    value: Any,
    actor_id: int | None = None,
    chat_id: int | None = None
) -> Any:
    value = _validate_value(key, value)
    definition = SETTINGS_SCHEMA[key]

    if chat_id is not None and not definition.per_chat:
        raise ValueError(f"{key} does not support per-chat override")

    now = datetime.now()
    serialized = _serialize(value)
    old_value: str | None = None

    if chat_id is not None:
        row = await _first_or_none(ChatSetting.objects.filter(chat_id=chat_id, key=key))
        if row:
            old_value = row.value
            row.value = serialized
            row.value_type = definition.value_type
            row.updated_by = actor_id
            row.updated_at = now
            await row.update()
        else:
            await ChatSetting.objects.create(
                chat_id=chat_id,
                key=key,
                value=serialized,
                value_type=definition.value_type,
                updated_by=actor_id,
                updated_at=now
            )
        _chat_cache[(chat_id, key)] = value
    else:
        row = await _first_or_none(BotSetting.objects.filter(key=key))
        if row:
            old_value = row.value
            row.value = serialized
            row.value_type = definition.value_type
            row.updated_by = actor_id
            row.updated_at = now
            await row.update()
        else:
            await BotSetting.objects.create(
                key=key,
                value=serialized,
                value_type=definition.value_type,
                updated_by=actor_id,
                updated_at=now
            )
        _global_cache[key] = value

    await SettingsAuditLog.objects.create(
        actor_id=actor_id,
        scope_type="chat" if chat_id is not None else "global",
        scope_id=chat_id,
        key=key,
        old_value=old_value,
        new_value=serialized,
        created_at=now
    )
    return value


async def reset_setting(
    key: str,
    actor_id: int | None = None,
    chat_id: int | None = None
) -> None:
    if key not in SETTINGS_SCHEMA:
        raise ValueError(f"Unknown setting key: {key}")

    if chat_id is not None:
        row = await _first_or_none(ChatSetting.objects.filter(chat_id=chat_id, key=key))
        old_value = row.value if row else None
        if row:
            await row.delete()
        _chat_cache.pop((chat_id, key), None)
        await SettingsAuditLog.objects.create(
            actor_id=actor_id,
            scope_type="chat",
            scope_id=chat_id,
            key=key,
            old_value=old_value,
            new_value=None,
            created_at=datetime.now()
        )
        return

    row = await _first_or_none(BotSetting.objects.filter(key=key))
    old_value = row.value if row else None
    if row:
        await row.delete()
    _global_cache.pop(key, None)
    await SettingsAuditLog.objects.create(
        actor_id=actor_id,
        scope_type="global",
        scope_id=None,
        key=key,
        old_value=old_value,
        new_value=None,
        created_at=datetime.now()
    )


async def get_logs_chat_id() -> int:
    return int(await get_setting("groups.logs"))


async def get_reports_chat_id() -> int:
    return int(await get_setting("groups.reports"))


def clear_settings_cache() -> None:
    _global_cache.clear()
    _chat_cache.clear()


async def bootstrap_runtime_defaults() -> None:
    """
    Ensure critical settings exist in DB for discoverability.
    Existing values are not overwritten.
    """
    for key in (
        "groups.reports",
        "groups.logs",
        "moderation.new_user_automute_enabled",
        "moderation.new_user_automute_seconds",
        "moderation.message_min_interval_sec",
        "moderation.interval_violation_action",
    ):
        existing = await _first_or_none(BotSetting.objects.filter(key=key))
        if not existing:
            await BotSetting.objects.create(
                key=key,
                value=_serialize(DEFAULTS[key]),
                value_type=SETTINGS_SCHEMA[key].value_type,
                updated_by=None,
                updated_at=datetime.now()
            )
