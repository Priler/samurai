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


@dataclass(frozen=True)
class SettingMeta:
    category: str
    title: str
    description: str
    input_mode: str  # toggle | seconds | number | choice
    panel_visible: bool = True


SETTINGS_SCHEMA: dict[str, SettingDef] = {
    # groups/channels
    "groups.reports": SettingDef("int", per_chat=False),
    "groups.logs": SettingDef("int", per_chat=False),
    # moderation runtime
    "groups.new_users_nomedia": SettingDef("int", min_value=0, max_value=31536000),
    "moderation.new_user_automute_enabled": SettingDef("bool"),
    "moderation.new_user_automute_seconds": SettingDef("int", min_value=0, max_value=31536000),
    "moderation.message_min_interval_sec": SettingDef("int", min_value=0, max_value=86400),
    "moderation.interval_violation_action": SettingDef("str"),
    "moderation.interval_penalty_points": SettingDef("int", min_value=0),
    "moderation.profanity_temp_ban_enabled": SettingDef("bool"),
    "moderation.profanity_temp_ban_seconds": SettingDef("int", min_value=0, max_value=31536000),
    # owner panel context
    "owner.active_chat_id": SettingDef("int", per_chat=False),
    # spam
    "spam.member_messages_threshold": SettingDef("int", min_value=0),
    "spam.member_reputation_threshold": SettingDef("int", min_value=-999999),
    "spam.allow_media_threshold": SettingDef("int", min_value=-999999),
    "spam.remove_first_comments_interval": SettingDef("int", min_value=0, max_value=31536000),
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
    "nsfw.profile_check_cooldown": SettingDef("int", min_value=0, max_value=31536000),
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

SETTINGS_META: dict[str, SettingMeta] = {
    "groups.new_users_nomedia": SettingMeta(
        "Новые участники",
        "Ограничение медиа для новых (сек)",
        "Сколько секунд после входа новым участникам запрещены медиа",
        "seconds"
    ),
    "moderation.new_user_automute_enabled": SettingMeta(
        "Новые участники", "Автомьют новых участников", "Включить/выключить автомьют новых пользователей", "toggle"
    ),
    "moderation.new_user_automute_seconds": SettingMeta(
        "Новые участники", "Длительность автомьюта (сек)", "Сколько секунд длится автомьют новых участников", "seconds"
    ),
    "moderation.message_min_interval_sec": SettingMeta(
        "Интервал сообщений", "Минимальный интервал (сек)", "Ограничение частоты сообщений в секундах (после второго сообщения менее чем через указанное количество секунд замьютит юзера на 30 сек). Если указать 0 - ограничения не будет", "seconds"
    ),
    "moderation.interval_violation_action": SettingMeta(
        "Интервал сообщений",
        "Действие при нарушении",
        "delete / warn / penalty",
        "choice",
        panel_visible=False
    ),
    "moderation.interval_penalty_points": SettingMeta(
        "Интервал сообщений",
        "Штраф репутации",
        "Сколько очков снимать при нарушении интервала",
        "number",
        panel_visible=False
    ),
    "moderation.profanity_temp_ban_enabled": SettingMeta(
        "Антимат", "Временный бан за мат", "Включить/выключить временный бан за мат", "toggle"
    ),
    "moderation.profanity_temp_ban_seconds": SettingMeta(
        "Антимат", "Длительность бана за мат (сек)", "Срок временного бана в секундах", "seconds"
    ),
    "spam.autoban_enabled": SettingMeta("Разные непонятные настройки", "Автобан", "Автобанить спамеров по порогам", "toggle"),
    "spam.autoban_threshold": SettingMeta("Разные непонятные настройки", "Порог автобана", "Минимум нарушений для автобана", "number"),
    "spam.autoban_rep_threshold": SettingMeta("Разные непонятные настройки", "Порог репутации для автобана", "Автобан только ниже этой репы", "number"),
    "spam.member_messages_threshold": SettingMeta(
        "Разные непонятные настройки",
        "Лимит сообщений для проверок",
        "После этого числа сообщений пользователь считается доверенным для антиспам-проверок",
        "number"
    ),
    "spam.member_reputation_threshold": SettingMeta(
        "Разные непонятные настройки",
        "Лимит репутации для проверок",
        "Если репутация выше порога, антиспам-проверки можно ослабить",
        "number"
    ),
    "spam.allow_media_threshold": SettingMeta("Разные непонятные настройки", "Порог медиа", "Минимальная репутация для медиа", "number"),
    "spam.remove_first_comments_interval": SettingMeta(
        "Разные непонятные настройки",
        "Удаление ранних комментариев (сек)",
        "В течение этого интервала после поста удаляются комментарии от низкорепутационных аккаунтов",
        "seconds"
    ),
    "spam.allow_comments_rep_threshold": SettingMeta(
        "Разные непонятные настройки",
        "Порог репутации для комментариев",
        "Минимальная репутация, чтобы писать комментарии к постам канала",
        "number"
    ),
    "spam.allow_comments_rep_threshold__woman": SettingMeta(
        "Разные непонятные настройки",
        "Порог репутации для комментариев (жен.)",
        "Отдельный порог репутации для женских аккаунтов в комментариях",
        "number"
    ),
    "spam.single_emoji_rep_threshold": SettingMeta(
        "Разные непонятные настройки",
        "Порог для одиночного эмодзи",
        "Сообщения из одного эмодзи удаляются, если репутация ниже порога",
        "number"
    ),
    "spam.links_rep_threshold": SettingMeta("Разные непонятные настройки", "Порог ссылок", "Минимальная репутация для ссылок", "number"),
    "spam.external_reply_rep_threshold": SettingMeta(
        "Разные непонятные настройки",
        "Порог cross-chat reply",
        "Минимальная репутация для Reply in Another Chat",
        "number"
    ),
    "spam.allow_forwards_threshold": SettingMeta("Разные непонятные настройки", "Порог форвардов", "Минимальная репутация для форвардов", "number"),
    "spam.forward_violation_penalty": SettingMeta("Разные непонятные настройки", "Штраф за форвард", "Штраф репутации за запрещенный форвард", "number"),
    "nsfw.enabled": SettingMeta("Разные непонятные настройки", "NSFW-проверка", "Включить/выключить NSFW модерацию", "toggle"),
    "nsfw.check_rep_threshold": SettingMeta("Разные непонятные настройки", "Порог репутации NSFW", "Кого проверять на NSFW по репутации", "number"),
    "nsfw.profile_check_cooldown": SettingMeta(
        "Разные непонятные настройки",
        "Кулдаун проверки профиля (сек)",
        "Минимальная пауза между проверками аватара одного пользователя",
        "seconds"
    ),
    "nsfw.comb_sensual_prediction_threshold": SettingMeta(
        "Разные непонятные настройки",
        "Порог sensual (комбинированный)",
        "Часть комбинированного условия NSFW по классу sensual",
        "number"
    ),
    "nsfw.comb_pornography_prediction_threshold": SettingMeta(
        "Разные непонятные настройки",
        "Порог pornography (комбинированный)",
        "Часть комбинированного условия NSFW по классу pornography",
        "number"
    ),
    "nsfw.sensual_prediction_threshold": SettingMeta(
        "Разные непонятные настройки",
        "Порог sensual",
        "NSFW срабатывает при превышении этого порога sensual",
        "number"
    ),
    "nsfw.pornography_prediction_threshold": SettingMeta(
        "Разные непонятные настройки",
        "Порог pornography",
        "NSFW срабатывает при превышении этого порога pornography",
        "number"
    ),
    "nsfw.hentai_prediction_threshold": SettingMeta(
        "Разные непонятные настройки",
        "Порог hentai",
        "Порог для класса hentai (учитывается вместе с другими сигналами)",
        "number"
    ),
    "nsfw.normal_prediction_threshold": SettingMeta(
        "Разные непонятные настройки",
        "Порог normal (safe)",
        "Высокий normal снижает вероятность NSFW-срабатывания",
        "number"
    ),
    "nsfw.normal_comb_sensual_prediction_threshold": SettingMeta(
        "Разные непонятные настройки",
        "Порог normal+sensual",
        "Часть safe-условия с normal и sensual",
        "number"
    ),
    "nsfw.normal_comb_pornography_prediction_threshold": SettingMeta(
        "Разные непонятные настройки",
        "Порог normal+pornography",
        "Часть safe-условия с normal и pornography",
        "number"
    ),
    "nsfw.anime_prediction_threshold": SettingMeta(
        "Разные непонятные настройки",
        "Порог anime (safe)",
        "Высокий anime может считаться безопасным условием",
        "number"
    ),
    "groups.logs": SettingMeta("Репорты и логи", "ID канала логов", "Куда отправлять логи модерации", "number", panel_visible=False),
    "groups.reports": SettingMeta("Репорты и логи", "ID канала репортов", "Куда отправлять репорты пользователей", "number", panel_visible=False),
    "throttling.enabled": SettingMeta(
        "Разные непонятные настройки",
        "Включить rate limit",
        "Включить/выключить ограничение частоты сообщений в личке",
        "toggle"
    ),
    "throttling.rate_limit": SettingMeta(
        "Разные непонятные настройки",
        "Минимальный интервал",
        "Минимальный интервал между сообщениями (секунды, допускаются дробные)",
        "number"
    ),
    "throttling.max_messages": SettingMeta(
        "Разные непонятные настройки",
        "Лимит сообщений в окне",
        "Максимум сообщений в заданном временном окне",
        "number"
    ),
    "throttling.time_window": SettingMeta(
        "Разные непонятные настройки",
        "Размер окна (сек)",
        "Длительность временного окна для rate limit",
        "seconds"
    ),
    "owner.active_chat_id": SettingMeta(
        "Служебные",
        "Активный чат владельца",
        "Внутренний ключ контекста owner-панели",
        "number",
        panel_visible=False
    ),
}

CATEGORY_ORDER: tuple[str, ...] = (
    "Новые участники",
    "Интервал сообщений",
    "Антимат",
    "Разные непонятные настройки",
    "Служебные",
    "Прочее",
)

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
    "owner.active_chat_id": 0,
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
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = raw

    if value_type == "int":
        return int(parsed)
    if value_type == "float":
        return float(parsed)
    if value_type == "bool":
        if isinstance(parsed, bool):
            return parsed
        return str(parsed).lower() in ("1", "true", "yes", "on")
    if value_type == "list":
        return parsed if isinstance(parsed, list) else []
    if isinstance(parsed, str):
        return parsed
    return str(parsed)


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


def get_setting_meta(key: str) -> SettingMeta:
    meta = SETTINGS_META.get(key)
    if meta:
        return meta
    return SettingMeta("Прочее", key, key, "number")


def list_setting_categories(include_internal: bool = False) -> list[str]:
    categories: set[str] = set()
    for key in SETTINGS_SCHEMA.keys():
        meta = get_setting_meta(key)
        if not include_internal and not meta.panel_visible:
            continue
        categories.add(meta.category)

    order_map = {name: idx for idx, name in enumerate(CATEGORY_ORDER)}
    return sorted(categories, key=lambda name: (order_map.get(name, len(CATEGORY_ORDER)), name))


def list_settings_in_category(category: str, include_internal: bool = False) -> list[str]:
    keys = []
    for key in SETTINGS_SCHEMA.keys():
        meta = get_setting_meta(key)
        if meta.category != category:
            continue
        if not include_internal and not meta.panel_visible:
            continue
        keys.append(key)
    return sorted(keys)


def format_setting_value(key: str, value: Any) -> str:
    meta = get_setting_meta(key)
    if meta.input_mode == "toggle":
        return "Вкл" if bool(value) else "Выкл"
    if meta.input_mode == "seconds":
        return f"{int(value)} сек"
    return str(value)


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
        "owner.active_chat_id",
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


async def list_recent_setting_changes(limit: int = 20, scope_chat_id: int | None = None) -> list[dict[str, Any]]:
    query = SettingsAuditLog.objects.order_by("-created_at")
    if scope_chat_id is not None:
        query = query.filter(scope_type="chat", scope_id=scope_chat_id)
    rows = await query.limit(limit).all()

    output: list[dict[str, Any]] = []
    for row in rows:
        key = row.key
        value_type = SETTINGS_SCHEMA.get(key, SettingDef("str")).value_type
        old_parsed = _deserialize(row.old_value, value_type) if row.old_value is not None else None
        new_parsed = _deserialize(row.new_value, value_type) if row.new_value is not None else None
        meta = get_setting_meta(key)
        output.append({
            "created_at": row.created_at,
            "actor_id": row.actor_id,
            "scope_type": row.scope_type,
            "scope_id": row.scope_id,
            "key": key,
            "title": meta.title,
            "category": meta.category,
            "old": format_setting_value(key, old_parsed) if old_parsed is not None else "∅",
            "new": format_setting_value(key, new_parsed) if new_parsed is not None else "∅",
        })
    return output
