"""
Personal/owner action handlers (ping, profanity check, message from bot, NSFW test).
"""
import asyncio
import io
import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np
import psutil
from PIL import Image
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ChatPermissions
from db.models import Member

from config import config
from filters import IsOwnerFilter, IsAdminFilter, InMainGroups
from services.chat_registry import (
    get_main_chat_ids,
    list_managed_chats,
    list_admin_chats,
    register_chat,
    disable_chat,
    set_chat_monitoring,
    add_linked_channel,
    remove_linked_channel,
    list_linked_channels,
)
from services.owners import list_owner_ids, add_owner, remove_owner, is_owner
from services.runtime_settings import (
    get_setting,
    set_setting,
    reset_setting,
    list_setting_keys,
    parse_setting_input,
    list_setting_categories,
    list_settings_in_category,
    get_setting_meta,
    format_setting_value,
    list_recent_setting_changes,
)
from services.nsfw import classify_explicit_content as nsfw_predict
from services.profanity import check_for_profanity
from utils import remove_prefix

router = Router(name="personal_actions")

# temp storage for pending msgs (auto-cleanup after 5 minutes)
# used by callbacks.py
pending_messages: dict[str, tuple[str, datetime]] = {}
MAX_PENDING_MESSAGES = 50


@dataclass
class OwnerDialogState:
    action: str
    payload: dict


owner_dialog_state: dict[int, OwnerDialogState] = {}
owner_ui_context: dict[int, dict[str, str]] = {}


def _cleanup_old_messages() -> None:
    """Remove messages older than 5 minutes and enforce size limit."""
    now = datetime.now()
    expired = [k for k, (_, ts) in pending_messages.items() if now - ts > timedelta(minutes=5)]
    for k in expired:
        del pending_messages[k]
    
    # if still over limit, drop oldest
    while len(pending_messages) > MAX_PENDING_MESSAGES:
        oldest_key = min(pending_messages, key=lambda k: pending_messages[k][1])
        del pending_messages[oldest_key]


async def _build_chat_keyboard(bot, msg_id: str) -> InlineKeyboardMarkup:
    """Build inline keyboard with chat names."""
    buttons = []
    main_chat_ids = await get_main_chat_ids()
    
    for chat_id in main_chat_ids:
        try:
            chat = await bot.get_chat(chat_id)
            chat_name = chat.title or f"Chat {chat_id}"
        except Exception:
            chat_name = f"Chat {chat_id}"
        
        buttons.append([InlineKeyboardButton(
            text=f"📤 {chat_name}",
            callback_data=f"msg_{msg_id}_{chat_id}"
        )])
    
    # send to all btn
    buttons.append([InlineKeyboardButton(
        text="📢 Отправить во все чаты",
        callback_data=f"msg_{msg_id}_all"
    )])
    
    # cancel btn
    buttons.append([InlineKeyboardButton(
        text="❌ Отмена",
        callback_data=f"msg_{msg_id}_cancel"
    )])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def _chat_display(bot, chat_id: int) -> str:
    """Human-readable chat label with fallback to id."""
    try:
        chat = await bot.get_chat(chat_id)
        name = chat.title or chat.full_name or chat.username or "Unknown"
        return f"{name} (<code>{chat_id}</code>)"
    except Exception:
        return f"<code>{chat_id}</code>"


async def _chat_button_title(bot, chat_id: int) -> str:
    """Short chat title for button text."""
    try:
        chat = await bot.get_chat(chat_id)
        name = chat.title or chat.full_name or str(chat_id)
        return name[:45]
    except Exception:
        return str(chat_id)


async def _chat_anchor(bot, chat_id: int) -> str:
    """Clickable chat title when Telegram link can be built."""
    try:
        chat = await bot.get_chat(chat_id)
        title = chat.title or chat.full_name or str(chat_id)
        username = getattr(chat, "username", None)
        if username:
            return f'<a href="https://t.me/{username}">{title}</a>'
        if chat.type == "private" and chat_id > 0:
            return f'<a href="tg://user?id={chat_id}">{title}</a>'
        if chat_id < 0 and str(chat_id).startswith("-100"):
            internal_id = str(chat_id)[4:]
            return f'<a href="https://t.me/c/{internal_id}/1">{title}</a>'
        return title
    except Exception:
        return str(chat_id)


def _chat_type_label(chat_type: str) -> str:
    if chat_type == "channel":
        return "Канал"
    if chat_type in ("group", "supergroup"):
        return "Группа"
    return "Чат"


async def _ensure_chat_registered(bot, chat_id: int, is_enabled: bool | None = None) -> None:
    """Fetch chat from Telegram and upsert into managed chats registry."""
    title = None
    chat_type = "supergroup"
    bot_status = "left"
    try:
        chat = await bot.get_chat(chat_id)
        title = chat.title or getattr(chat, "full_name", None)
        chat_type = chat.type
        me = await bot.get_me()
        try:
            member = await bot.get_chat_member(chat_id, me.id)
            bot_status = member.status
        except Exception:
            bot_status = "left"
    except Exception:
        pass
    await register_chat(
        chat_id=chat_id,
        chat_type=chat_type,
        title=title,
        bot_status=bot_status,
        is_enabled=is_enabled,
    )


async def _resolve_linked_group_channel(bot, chat_id: int) -> tuple[int, int] | None:
    """
    Resolve Telegram native linked pair via linked_chat_id.
    Returns (group_chat_id, channel_chat_id) when available.
    """
    try:
        chat = await bot.get_chat(chat_id)
    except Exception:
        return None

    linked_chat_id = getattr(chat, "linked_chat_id", None)
    if not linked_chat_id:
        return None

    try:
        linked = await bot.get_chat(linked_chat_id)
    except Exception:
        return None

    if chat.type == "channel" and linked.type in ("group", "supergroup"):
        return linked_chat_id, chat_id
    if chat.type in ("group", "supergroup") and linked.type == "channel":
        return chat_id, linked_chat_id
    return None


async def _user_display(bot, user_id: int) -> str:
    """Human-readable user label with fallback to id."""
    try:
        user_chat = await bot.get_chat(user_id)
        name = user_chat.full_name or getattr(user_chat, "username", None) or "Unknown"
        username = getattr(user_chat, "username", None)
        if username:
            return f"{name} (@{username}, <code>{user_id}</code>)"
        return f"{name} (<code>{user_id}</code>)"
    except Exception:
        return f"<code>{user_id}</code>"


def _owner_home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧩 Чаты и каналы", callback_data="own_chats")],
        # [InlineKeyboardButton(text="🛠 Настройки модерации", callback_data="own_settings")],
        [InlineKeyboardButton(text="📨 Репорты и логи", callback_data="own_reports")],
        # [InlineKeyboardButton(text="🧾 История изменений", callback_data="own_audit")],
        [InlineKeyboardButton(text="👑 Владельцы", callback_data="own_owners")],
        [InlineKeyboardButton(text="⚡ Быстрые действия", callback_data="own_quick")],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="own_home")],
    ])


def _owner_nav_keyboard(back_cb: str = "own_home") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⬅ Назад", callback_data=back_cb),
            InlineKeyboardButton(text="🏠 Домой", callback_data="own_home"),
        ]
    ])


def _owner_settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧭 Выбрать и настроить чат", callback_data="own_chat_select_active")],
        [InlineKeyboardButton(text="🏠 Домой", callback_data="own_home")],
    ])


def _owner_chats_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚙️ Подключить/отключить", callback_data="own_chat_add")],
        [InlineKeyboardButton(text="🛠 Выбрать и настроить чат", callback_data="own_chat_select_active")],
        [InlineKeyboardButton(text="🏠 Домой", callback_data="own_home")],
    ])


def _owner_links_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить связку", callback_data="own_link_add")],
        [InlineKeyboardButton(text="➖ Удалить связку", callback_data="own_link_rm")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="own_chats")],
    ])


def _owner_monitor_intro_keyboard(back_cb: str = "own_chats") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить список чатов", callback_data="own_monitor_refresh")],
        [InlineKeyboardButton(text="➕ Подключить группу/канал к мониторингу", callback_data="own_monitor_add_group")],
        [InlineKeyboardButton(text="➖ Отключить группу/канал от мониторинга",
                              callback_data="own_monitor_remove_group")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data=back_cb)],
        [InlineKeyboardButton(text="🏠 Домой", callback_data="own_home")],
    ])


def _owner_monitor_groups_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕️ Подключить группу/канал к мониторингу", callback_data="own_monitor_add_group")],
        [InlineKeyboardButton(text="➖ Отключить группу/канал от мониторинга", callback_data="own_monitor_remove_group")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="own_chat_add")],
    ])


def _owner_owners_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить owner", callback_data="own_owner_add")],
        [InlineKeyboardButton(text="➖ Удалить owner", callback_data="own_owner_rm")],
        [InlineKeyboardButton(text="🏠 Домой", callback_data="own_home")],
    ])


def _owner_reports_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧪 Тест лога", callback_data="own_test_log")],
        [InlineKeyboardButton(text="🧪 Тест репорт-канала", callback_data="own_test_reports")],
        [InlineKeyboardButton(text="🏠 Домой", callback_data="own_home")],
    ])


def _owner_quick_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📣 Рассылка в чаты", callback_data="own_quick_broadcast")],
        # [InlineKeyboardButton(text="🙊 Автомьют ON", callback_data="own_quick_automute_on")],
        # [InlineKeyboardButton(text="🔓 Автомьют OFF", callback_data="own_quick_automute_off")],
        # [InlineKeyboardButton(text="⏱ Интервал 60с", callback_data="own_quick_interval_60")],
        # [InlineKeyboardButton(text="⏱ Интервал OFF", callback_data="own_quick_interval_0")],
        [InlineKeyboardButton(text="🏠 Домой", callback_data="own_home")],
    ])


async def _get_active_chat_id(user_id: int) -> int | None:
    try:
        return int(await get_setting("owner.active_chat_id", chat_id=None))
    except Exception:
        return None


async def _set_active_chat_id(user_id: int, chat_id: int) -> None:
    await set_setting("owner.active_chat_id", chat_id, actor_id=user_id, chat_id=None)


def _get_scope(user_id: int) -> str:
    return owner_ui_context.get(user_id, {}).get("scope", "global")


def _set_scope(user_id: int, scope: str) -> None:
    owner_ui_context.setdefault(user_id, {})["scope"] = scope


async def _resolve_scope_chat_id(user_id: int) -> int | None:
    if _get_scope(user_id) == "global":
        return None
    return await _get_active_chat_id(user_id)


def _setting_edit_keyboard(key: str, back_cb: str) -> InlineKeyboardMarkup:
    meta = get_setting_meta(key)
    buttons: list[list[InlineKeyboardButton]] = []
    if meta.input_mode == "toggle":
        buttons.append([
            InlineKeyboardButton(text="✅ Включить", callback_data=f"own_set_toggle_{key}_1"),
            InlineKeyboardButton(text="⛔ Выключить", callback_data=f"own_set_toggle_{key}_0"),
        ])
    elif meta.input_mode == "choice" and key == "moderation.interval_violation_action":
        buttons.append([
            InlineKeyboardButton(text="Удалять", callback_data=f"own_set_choice_{key}_delete"),
            InlineKeyboardButton(text="Предупреждать", callback_data=f"own_set_choice_{key}_warn"),
        ])
        buttons.append([
            InlineKeyboardButton(text="Штраф", callback_data=f"own_set_choice_{key}_penalty"),
        ])
    else:
        buttons.append([InlineKeyboardButton(text="✍ Ввести значение", callback_data=f"own_set_input_{key}")])
    buttons.append([InlineKeyboardButton(text="♻ Сбросить к дефолту", callback_data=f"own_set_reset_{key}")])
    buttons.append([
        InlineKeyboardButton(text="⬅ Назад", callback_data=back_cb),
        InlineKeyboardButton(text="🏠 Домой", callback_data="own_home"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _panel_categories_keyboard() -> InlineKeyboardMarkup:
    categories = list_setting_categories()
    buttons = [
        [InlineKeyboardButton(text=category, callback_data=f"own_setcat_{idx}")]
        for idx, category in enumerate(categories)
    ]
    buttons.extend(_settings_moderation_buttons())
    buttons.append([InlineKeyboardButton(text="🧭 Выбрать и настроить чат", callback_data="own_chat_select_active")])
    buttons.append([InlineKeyboardButton(text="🏠 Домой", callback_data="own_home")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def _settings_chat_header(bot, chat_id: int) -> str:
    return (
        "🛠 <b>Настраиваем чат...</b>\n"
        f"{await _chat_anchor(bot, chat_id)}"
    )


async def _render_settings_categories_text(bot, chat_id: int) -> str:
    return (
        f"{await _settings_chat_header(bot, chat_id)}\n\n"
        "📂 <b>Категории настроек</b>\n"
        "Выберите раздел:"
    )


def _settings_category_keyboard(category: str) -> InlineKeyboardMarkup:
    keys = list_settings_in_category(category)
    buttons = [
        [InlineKeyboardButton(text=get_setting_meta(key).title[:45], callback_data=f"own_set_edit_{key}")]
        for key in keys
    ]
    buttons.extend(_settings_moderation_buttons())
    buttons.append([InlineKeyboardButton(text="⬅ К категориям", callback_data="own_cfg_categories")])
    buttons.append([InlineKeyboardButton(text="🏠 Домой", callback_data="own_home")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _settings_moderation_buttons() -> list[list[InlineKeyboardButton]]:
    return [
        [
            InlineKeyboardButton(text="🙊 Мьют всех на 5 минут", callback_data="own_mass_mute_300"),
            InlineKeyboardButton(text="🙊 Мьют всех на 1 час", callback_data="own_mass_mute_3600"),
        ],
        [InlineKeyboardButton(text="🔓 Размьютить всех", callback_data="own_mass_unmute_all")],
        [InlineKeyboardButton(text="🚫 Разбан", callback_data="own_unban_menu_0")],
    ]


def _unmute_permissions() -> ChatPermissions:
    return ChatPermissions(can_send_messages=True)


async def _known_banned_members(bot, chat_id: int, scan_limit: int = 500) -> list[int]:
    rows = await Member.objects.order_by("-id").limit(scan_limit).all()
    banned: list[int] = []
    for row in rows:
        user_id = row.user_id
        try:
            member = await bot.get_chat_member(chat_id, user_id)
        except Exception:
            continue
        if member.status == "kicked":
            banned.append(user_id)
    return banned


async def _user_button_title(bot, user_id: int) -> str:
    try:
        user = await bot.get_chat(user_id)
        title = user.full_name or getattr(user, "username", None) or str(user_id)
        return title[:45]
    except Exception:
        return str(user_id)


async def _render_unban_menu(call: CallbackQuery, chat_id: int, page: int) -> None:
    banned_ids = await _known_banned_members(call.bot, chat_id)
    per_page = 8
    pages = max(1, (len(banned_ids) + per_page - 1) // per_page)
    page = max(0, min(page, pages - 1))
    start = page * per_page
    chunk = banned_ids[start:start + per_page]

    lines = [await _settings_chat_header(call.bot, chat_id), "", "🚫 <b>Разбан</b>"]
    if not banned_ids:
        lines.append("Забаненных пользователей не найдено.")
    else:
        lines.append(f"Страница {page + 1}/{pages}")
        for user_id in chunk:
            lines.append(f"• {await _user_display(call.bot, user_id)}")

    buttons: list[list[InlineKeyboardButton]] = []
    for user_id in chunk:
        buttons.append([
            InlineKeyboardButton(
                text=f"♻️ Разбанить {await _user_button_title(call.bot, user_id)}",
                callback_data=f"own_unban_user_{user_id}_{page}",
            )
        ])

    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"own_unban_menu_{page - 1}"))
    if page < pages - 1:
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"own_unban_menu_{page + 1}"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton(text="♻️ Разбанить всех", callback_data="own_unban_all")])
    buttons.append([InlineKeyboardButton(text="⬅ Назад в настройки", callback_data="own_cfg_categories")])
    buttons.append([InlineKeyboardButton(text="🏠 Домой", callback_data="own_home")])
    await call.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


async def _render_settings_category_text(bot, chat_id: int, category: str) -> str:
    lines = [await _settings_chat_header(bot, chat_id), "", f"📂 <b>{category}</b>", ""]
    for key in list_settings_in_category(category):
        value = await get_setting(key, chat_id=chat_id)
        meta = get_setting_meta(key)
        lines.append(f"• <b>{meta.title}</b>: <code>{format_setting_value(key, value)}</code>")
        lines.append(f"  <i>{meta.description}</i>")
    if not list_settings_in_category(category):
        lines.append("Параметров в категории нет.")
    return "\n".join(lines)


async def _build_owner_home_text() -> str:
    monitored = await list_managed_chats(enabled_only=True)
    admin_chats = await list_admin_chats()
    links = await list_linked_channels()
    auto_mute = bool(await get_setting("moderation.new_user_automute_enabled"))
    auto_mute_seconds = int(await get_setting("moderation.new_user_automute_seconds"))
    interval = int(await get_setting("moderation.message_min_interval_sec"))
    profanity_ban = bool(await get_setting("moderation.profanity_temp_ban_enabled"))
    return (
        "👋 <b>Панель управления модератором Педро</b>\n\n"      
        "Бот умеет:\n"
        "- ограничивать активность новых пользователей\n"
        "- чистить мат\n"
        "- бороться со спамом\n"
        "- проверять изображения и картинки в профилях\n"
        "- распознавать токсичное поведение (хех - пока ещё не умеет)\n"
        "- устанавливать ограничения на сообщения (интервал, количество)\n"
        "- вести рейтинг пользователей (зачем-то)\n"
        "- ещё что-то, о чем мы сами не особо знаем (вроде как даже шутит по команде <b>!бу</b>)\n\n"
        f"🧩 Групп мониторинга: <b>{len(monitored)}</b>\n"
        f"🛡 Чатов/каналов где бот админ: <b>{len(admin_chats)}</b>\n"
        f"🔗 Связанных каналов: <b>{len(links)}</b>\n"
    )


@router.message(F.chat.type == "private", Command("start"))
async def cmd_start_private(message: Message) -> None:
    """Start command with owner/non-owner split."""
    if await is_owner(message.from_user.id):
        owner_dialog_state.pop(message.from_user.id, None)
        await message.reply(
            await _build_owner_home_text(),
            reply_markup=_owner_home_keyboard()
        )
    else:
        await message.reply(
            "Привет. Этот бот используется для модерации групп.\n"
            "Управление доступно только владельцам."
        )


@router.callback_query(F.data.startswith("own_"))
async def callback_owner_panel(call: CallbackQuery) -> None:
    """Owner panel navigation and actions."""
    if not await is_owner(call.from_user.id):
        await call.answer("⛔ Только для владельца", show_alert=True)
        return

    owner_dialog_state.pop(call.from_user.id, None)
    data = call.data

    if data == "own_home":
        await call.message.edit_text(await _build_owner_home_text(), reply_markup=_owner_home_keyboard())
        await call.answer()
        return

    if data == "own_monitor_intro":
        await call.message.edit_text(
            "🧭 <b>Подключить канал/группу на мониторинг</b>\n\n"
            "Чтобы подключить группу или канал, бот должен быть туда добавлен как <b>администратор</b>.\n"
            "1) Добавьте бота админом в нужный чат/канал.\n"
            "2) Нажмите «Обновить список чатов».\n"
            "3) Перейдите к выбору групп мониторинга.\n",
            reply_markup=_owner_monitor_intro_keyboard("own_chats")
        )
        await call.answer()
        return

    if data == "own_monitor_refresh":
        admin_count = 0
        member_count = 0
        me = await call.bot.get_me()
        for row in await list_managed_chats(enabled_only=False):
            try:
                member = await call.bot.get_chat_member(row.chat_id, me.id)
                status = member.status
                if status in ("administrator", "creator"):
                    admin_count += 1
                elif status == "member":
                    member_count += 1
                await register_chat(
                    chat_id=row.chat_id,
                    chat_type=row.chat_type,
                    title=row.title,
                    bot_status=status,
                    is_enabled=row.is_enabled
                )
            except Exception:
                await register_chat(
                    chat_id=row.chat_id,
                    chat_type=row.chat_type,
                    title=row.title,
                    bot_status="left",
                    is_enabled=False
                )
        await call.answer(f"Обновлено. admin: {admin_count}, member: {member_count}")
        await call.message.edit_text(
            "✅ Список чатов обновлён.\n"
            f"Где бот админ: <b>{admin_count}</b>\n"
            f"Где бот просто участник: <b>{member_count}</b>",
            reply_markup=_owner_monitor_intro_keyboard("own_chats")
        )
        return

    if data == "own_monitor_groups":
        admin_groups = [c for c in await list_admin_chats() if c.chat_type in ("group", "supergroup")]
        monitored = [c for c in admin_groups if c.is_enabled]
        lines = ["🧩 <b>Группы для мониторинга</b>"]
        lines.append(f"Бот админ в группах: <b>{len(admin_groups)}</b>")
        lines.append(f"Мониторится: <b>{len(monitored)}</b>\n")
        for row in monitored[:20]:
            lines.append(f"• {await _chat_display(call.bot, row.chat_id)}")
        await call.message.edit_text("\n".join(lines), reply_markup=_owner_monitor_groups_keyboard())
        await call.answer()
        return

    if data == "own_monitor_select_active":
        monitored = [c for c in await list_admin_chats() if c.chat_type in ("group", "supergroup") and c.is_enabled]
        buttons = [[InlineKeyboardButton(text=await _chat_button_title(call.bot, row.chat_id), callback_data=f"own_active_{row.chat_id}")]
                   for row in monitored[:30]]
        buttons.append([InlineKeyboardButton(text="⬅ Назад", callback_data="own_monitor_groups")])
        await call.message.edit_text(
            "Выберите группу мониторинга для изменения параметров:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await call.answer()
        return

    if data == "own_monitor_add_group":
        candidates = [c for c in await list_admin_chats() if c.chat_type in ("group", "supergroup", "channel") and not c.is_enabled]
        buttons = [[InlineKeyboardButton(
            text=f"{await _chat_button_title(call.bot, row.chat_id)} ({_chat_type_label(row.chat_type)})",
            callback_data=f"own_mon_add_{row.chat_id}"
        )]
                   for row in candidates[:30]]
        buttons.append([InlineKeyboardButton(text="⬅ Назад", callback_data="own_chat_add")])
        await call.message.edit_text(
            "Выберите группу или канал, которые нужно добавить в мониторинг:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await call.answer()
        return

    if data.startswith("own_mon_add_"):
        chat_id = int(data.replace("own_mon_add_", ""))
        changed = await set_chat_monitoring(chat_id, True)
        if not changed:
            await call.answer("Группа не найдена")
            await call.message.edit_text("ℹ️ Группа не найдена.", reply_markup=_owner_monitor_groups_keyboard())
            return

        extra = ""
        linked_pair = await _resolve_linked_group_channel(call.bot, chat_id)
        if linked_pair:
            group_id, channel_id = linked_pair
            await _ensure_chat_registered(call.bot, group_id, is_enabled=True)
            await _ensure_chat_registered(call.bot, channel_id, is_enabled=True)
            await set_chat_monitoring(group_id, True)
            await set_chat_monitoring(channel_id, True)
            await add_linked_channel(group_id, channel_id, source="owner-panel:auto-link")
            group_name = await _chat_anchor(call.bot, group_id)
            channel_name = await _chat_anchor(call.bot, channel_id)
            extra = (
                "\n🔗 Автоматически добавлена связанная пара:"
                f"\n• Группа: {group_name}"
                f"\n• Канал: {channel_name}"
            )

        await call.answer("Добавлено")
        await call.message.edit_text(
            "✅ Объект добавлен в мониторинг." + extra,
            reply_markup=_owner_monitor_groups_keyboard()
        )
        return

    if data == "own_monitor_remove_group":
        candidates = [c for c in await list_managed_chats(enabled_only=True) if c.chat_type in ("group", "supergroup", "channel")]
        buttons = [[InlineKeyboardButton(
            text=f"{await _chat_button_title(call.bot, row.chat_id)} ({_chat_type_label(row.chat_type)})",
            callback_data=f"own_mon_rm_{row.chat_id}"
        )]
                   for row in candidates[:30]]
        buttons.append([InlineKeyboardButton(text="⬅ Назад", callback_data="own_monitor_groups")])
        await call.message.edit_text(
            "Выберите группу или канал, которые нужно исключить из мониторинга:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await call.answer()
        return

    if data.startswith("own_mon_rm_"):
        chat_id = int(data.replace("own_mon_rm_", ""))
        changed = await set_chat_monitoring(chat_id, False)
        await call.answer("Исключено" if changed else "Объект не найден")
        await call.message.edit_text("✅ Объект исключён из мониторинга.", reply_markup=_owner_monitor_groups_keyboard())
        return

    if data == "own_monitor_add_channel":
        groups = [c for c in await list_managed_chats(enabled_only=True) if c.chat_type in ("group", "supergroup")]
        buttons = [[InlineKeyboardButton(text=await _chat_button_title(call.bot, row.chat_id), callback_data=f"own_mon_link_group_{row.chat_id}")]
                   for row in groups[:30]]
        buttons.append([InlineKeyboardButton(text="⬅ Назад", callback_data="own_monitor_groups")])
        await call.message.edit_text(
            "Шаг 1/2. Выберите группу мониторинга для привязки канала:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await call.answer()
        return

    if data.startswith("own_mon_link_group_"):
        group_id = int(data.replace("own_mon_link_group_", ""))
        channels = [c for c in await list_admin_chats(chat_type="channel")]
        buttons = [
            [InlineKeyboardButton(
                text=await _chat_button_title(call.bot, row.chat_id),
                callback_data=f"own_mon_link_channel_{group_id}_{row.chat_id}"
            )]
            for row in channels[:30]
        ]
        buttons.append([InlineKeyboardButton(text="⬅ Назад", callback_data="own_monitor_add_channel")])
        await call.message.edit_text(
            "Шаг 2/2. Выберите канал (бот должен быть админом):",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await call.answer()
        return

    if data.startswith("own_mon_link_channel_"):
        payload = data.replace("own_mon_link_channel_", "", 1)
        group_s, channel_s = payload.split("_", maxsplit=1)
        selected_group_id = int(group_s)
        selected_channel_id = int(channel_s)

        linked_pair = await _resolve_linked_group_channel(call.bot, selected_channel_id)
        if linked_pair:
            group_id, channel_id = linked_pair
            await _ensure_chat_registered(call.bot, group_id, is_enabled=True)
            await _ensure_chat_registered(call.bot, channel_id)
            await set_chat_monitoring(group_id, True)
            await add_linked_channel(group_id, channel_id, source="owner-panel:auto-link")
            note = ""
            if group_id != selected_group_id:
                note = (
                    "\nℹ️ Выбранный канал уже связан в Telegram с другой группой, "
                    "поэтому использована нативная связка."
                )
            await call.answer("Связка добавлена")
            group_name = await _chat_anchor(call.bot, group_id)
            channel_name = await _chat_anchor(call.bot, channel_id)
            await call.message.edit_text(
                "✅ Канал привязан к группе мониторинга."
                f"\nГруппа: {group_name}\nКанал: {channel_name}" + note,
                reply_markup=_owner_monitor_groups_keyboard()
            )
            return

        await add_linked_channel(selected_group_id, selected_channel_id, source="owner-panel")
        await call.answer("Связка добавлена")
        await call.message.edit_text(
            "✅ Канал привязан к группе мониторинга.",
            reply_markup=_owner_monitor_groups_keyboard()
        )
        return

    if data == "own_chats":
        managed = await list_managed_chats(enabled_only=True)
        chats = [row for row in managed if row.chat_type in ("group", "supergroup")]
        channels = [row for row in managed if row.chat_type == "channel"]
        lines = ["🧩 <b>Чаты в управлении</b>"]
        if chats:
            for row in chats[:25]:
                lines.append(f"• {await _chat_anchor(call.bot, row.chat_id)}")
        else:
            lines.append("Список пуст.")
        lines.append("")
        lines.append("🔗 <b>Каналы</b>")
        if channels:
            seen_channel_ids: set[int] = set()
            count = 0
            for row in channels:
                if row.chat_id in seen_channel_ids:
                    continue
                seen_channel_ids.add(row.chat_id)
                lines.append(f"• {await _chat_anchor(call.bot, row.chat_id)}")
                count += 1
                if count >= 25:
                    break
        else:
            lines.append("Список пуст.")
        await call.message.edit_text("\n".join(lines), reply_markup=_owner_chats_keyboard())
        await call.answer()
        return

    if data == "own_links":
        rows = await list_linked_channels()
        lines = ["🔗 <b>Связанные каналы</b>"]
        if rows:
            for row in rows[:25]:
                lines.append(
                    f"- {await _chat_display(call.bot, row.group_chat_id)} -> "
                    f"{await _chat_display(call.bot, row.channel_chat_id)}"
                )
        else:
            lines.append("Список пуст.")
        await call.message.edit_text("\n".join(lines), reply_markup=_owner_links_keyboard())
        await call.answer()
        return

    if data == "own_owners":
        owners = await list_owner_ids()
        owner_lines = [f"- {await _user_display(call.bot, uid)}" for uid in owners]
        await call.message.edit_text(
            "👑 <b>Владельцы</b>\n" + "\n".join(owner_lines),
            reply_markup=_owner_owners_keyboard()
        )
        await call.answer()
        return

    if data == "own_settings":
        active_chat = await _get_active_chat_id(call.from_user.id)
        if not active_chat:
            await call.message.edit_text(
                "🛠 <b>Настройки модерации</b>\nВыберите чат для настройки.",
                reply_markup=_owner_settings_keyboard()
            )
            await call.answer()
            return
        _set_scope(call.from_user.id, "chat")
        await call.message.edit_text(
            await _render_settings_categories_text(call.bot, active_chat),
            reply_markup=_panel_categories_keyboard()
        )
        await call.answer()
        return

    if data == "own_cfg_categories":
        active_chat = await _get_active_chat_id(call.from_user.id)
        if not active_chat:
            await call.answer("Сначала выберите чат для настройки", show_alert=True)
            return
        await call.message.edit_text(
            await _render_settings_categories_text(call.bot, active_chat),
            reply_markup=_panel_categories_keyboard()
        )
        await call.answer()
        return

    if data.startswith("own_setcat_"):
        idx = int(data.replace("own_setcat_", ""))
        categories = list_setting_categories()
        if idx < 0 or idx >= len(categories):
            await call.answer("Категория не найдена", show_alert=True)
            return
        category = categories[idx]
        active_chat = await _get_active_chat_id(call.from_user.id)
        if not active_chat:
            await call.answer("Сначала выберите чат для настройки", show_alert=True)
            return
        await call.message.edit_text(
            await _render_settings_category_text(call.bot, active_chat, category),
            reply_markup=_settings_category_keyboard(category)
        )
        await call.answer()
        return

    if data.startswith("own_set_edit_"):
        key = data.replace("own_set_edit_", "", 1)
        meta = get_setting_meta(key)
        chat_id = await _get_active_chat_id(call.from_user.id)
        if not chat_id:
            await call.answer("Сначала выберите чат для настройки", show_alert=True)
            return
        value = await get_setting(key, chat_id=chat_id)
        prompt = (
            f"{await _settings_chat_header(call.bot, chat_id)}\n\n"
            f"⚙ <b>{meta.title}</b>\n"
            f"{meta.description}\n\n"
            f"Текущее значение: <code>{format_setting_value(key, value)}</code>\n"
        )
        if meta.input_mode == "seconds":
            prompt += "\nВведите значение только в <b>секундах</b>."
        elif meta.input_mode == "number":
            prompt += "\nВведите числовое значение."
        elif meta.input_mode == "choice":
            prompt += "\nВыберите один из вариантов кнопками."
        else:
            prompt += "\nВключение/выключение доступно только кнопками."
        await call.message.edit_text(
            prompt,
            reply_markup=_setting_edit_keyboard(key, "own_cfg_categories")
        )
        await call.answer()
        return

    if data.startswith("own_set_toggle_"):
        payload = data.replace("own_set_toggle_", "", 1)
        key, raw = payload.rsplit("_", maxsplit=1)
        value = raw == "1"
        chat_id = await _get_active_chat_id(call.from_user.id)
        if not chat_id:
            await call.answer("Сначала выберите чат для настройки", show_alert=True)
            return
        await set_setting(key, value, actor_id=call.from_user.id, chat_id=chat_id)
        await call.answer("Сохранено")
        await call.message.edit_text(
            f"{await _settings_chat_header(call.bot, chat_id)}\n\n"
            f"✅ <b>{get_setting_meta(key).title}</b>: <code>{format_setting_value(key, value)}</code>",
            reply_markup=_setting_edit_keyboard(key, "own_cfg_categories")
        )
        return

    if data.startswith("own_set_choice_"):
        payload = data.replace("own_set_choice_", "", 1)
        key, choice = payload.rsplit("_", maxsplit=1)
        chat_id = await _get_active_chat_id(call.from_user.id)
        if not chat_id:
            await call.answer("Сначала выберите чат для настройки", show_alert=True)
            return
        await set_setting(key, choice, actor_id=call.from_user.id, chat_id=chat_id)
        await call.answer("Сохранено")
        await call.message.edit_text(
            f"{await _settings_chat_header(call.bot, chat_id)}\n\n"
            f"✅ <b>{get_setting_meta(key).title}</b>: <code>{format_setting_value(key, choice)}</code>",
            reply_markup=_setting_edit_keyboard(key, "own_cfg_categories")
        )
        return

    if data.startswith("own_set_reset_"):
        key = data.replace("own_set_reset_", "", 1)
        chat_id = await _get_active_chat_id(call.from_user.id)
        if not chat_id:
            await call.answer("Сначала выберите чат для настройки", show_alert=True)
            return
        await reset_setting(key, actor_id=call.from_user.id, chat_id=chat_id)
        current = await get_setting(key, chat_id=chat_id)
        await call.answer("Сброшено")
        await call.message.edit_text(
            f"{await _settings_chat_header(call.bot, chat_id)}\n\n"
            f"♻ <b>{get_setting_meta(key).title}</b> сброшено.\n"
            f"Текущее значение: <code>{format_setting_value(key, current)}</code>",
            reply_markup=_setting_edit_keyboard(key, "own_cfg_categories")
        )
        return

    if data.startswith("own_set_input_"):
        key = data.replace("own_set_input_", "", 1)
        chat_id = await _get_active_chat_id(call.from_user.id)
        if not chat_id:
            await call.answer("Сначала выберите чат для настройки", show_alert=True)
            return
        owner_dialog_state[call.from_user.id] = OwnerDialogState("cfg_set_smart", {"key": key, "chat_id": chat_id})
        await call.message.edit_text(
            f"{await _settings_chat_header(call.bot, chat_id)}\n\n"
            f"Введите значение для <b>{get_setting_meta(key).title}</b>.\n"
            "Для времени используйте только секунды.",
            reply_markup=_owner_nav_keyboard("own_cfg_categories")
        )
        await call.answer()
        return

    if data.startswith("own_mass_mute_"):
        chat_id = await _get_active_chat_id(call.from_user.id)
        if not chat_id:
            await call.answer("Сначала выберите чат для настройки", show_alert=True)
            return
        mute_seconds = int(data.replace("own_mass_mute_", ""))
        owner_ids = set(await list_owner_ids())
        rows = await Member.objects.order_by("-id").limit(1000).all()
        muted = 0
        for row in rows:
            user_id = row.user_id
            if user_id in owner_ids:
                continue
            try:
                member = await call.bot.get_chat_member(chat_id, user_id)
            except Exception:
                continue
            if member.status in ("administrator", "creator", "left", "kicked"):
                continue
            if getattr(member.user, "is_bot", False):
                continue
            try:
                await call.bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=datetime.now(timezone.utc) + timedelta(seconds=mute_seconds),
                )
                muted += 1
            except Exception:
                continue

        await call.message.edit_text(
            f"{await _settings_chat_header(call.bot, chat_id)}\n\n"
            f"✅ Мьют применён. Пользователей: <b>{muted}</b>.",
            reply_markup=_panel_categories_keyboard()
        )
        await call.answer("Готово")
        return

    if data == "own_mass_unmute_all":
        chat_id = await _get_active_chat_id(call.from_user.id)
        if not chat_id:
            await call.answer("Сначала выберите чат для настройки", show_alert=True)
            return
        rows = await Member.objects.order_by("-id").limit(1000).all()
        unmuted = 0
        for row in rows:
            user_id = row.user_id
            try:
                member = await call.bot.get_chat_member(chat_id, user_id)
            except Exception:
                continue
            if member.status != "restricted":
                continue
            try:
                await call.bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    permissions=_unmute_permissions(),
                )
                unmuted += 1
            except Exception:
                continue
        await call.message.edit_text(
            f"{await _settings_chat_header(call.bot, chat_id)}\n\n"
            f"✅ Размьючено пользователей: <b>{unmuted}</b>.",
            reply_markup=_panel_categories_keyboard()
        )
        await call.answer("Готово")
        return

    if data.startswith("own_unban_menu_"):
        chat_id = await _get_active_chat_id(call.from_user.id)
        if not chat_id:
            await call.answer("Сначала выберите чат для настройки", show_alert=True)
            return
        page = int(data.replace("own_unban_menu_", ""))
        await _render_unban_menu(call, chat_id, page)
        await call.answer()
        return

    if data.startswith("own_unban_user_"):
        chat_id = await _get_active_chat_id(call.from_user.id)
        if not chat_id:
            await call.answer("Сначала выберите чат для настройки", show_alert=True)
            return
        payload = data.replace("own_unban_user_", "", 1)
        user_s, page_s = payload.rsplit("_", maxsplit=1)
        user_id = int(user_s)
        page = int(page_s)
        try:
            await call.bot.unban_chat_member(chat_id=chat_id, user_id=user_id, only_if_banned=True)
            await call.answer("Пользователь разбанен")
        except Exception:
            await call.answer("Не удалось разбанить", show_alert=True)
        await _render_unban_menu(call, chat_id, page)
        return

    if data == "own_unban_all":
        chat_id = await _get_active_chat_id(call.from_user.id)
        if not chat_id:
            await call.answer("Сначала выберите чат для настройки", show_alert=True)
            return
        banned_ids = await _known_banned_members(call.bot, chat_id)
        unbanned = 0
        for user_id in banned_ids:
            try:
                await call.bot.unban_chat_member(chat_id=chat_id, user_id=user_id, only_if_banned=True)
                unbanned += 1
            except Exception:
                continue
        await call.message.edit_text(
            f"{await _settings_chat_header(call.bot, chat_id)}\n\n"
            f"✅ Разбанено пользователей: <b>{unbanned}</b>.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🚫 Открыть список разбанов", callback_data="own_unban_menu_0")],
                [InlineKeyboardButton(text="⬅ Назад в настройки", callback_data="own_cfg_categories")],
                [InlineKeyboardButton(text="🏠 Домой", callback_data="own_home")],
            ])
        )
        await call.answer("Готово")
        return

    if data == "own_audit":
        changes = await list_recent_setting_changes(limit=15)
        lines = ["🧾 <b>Последние изменения</b>"]
        if not changes:
            lines.append("Изменений пока нет.")
        for item in changes:
            ts = item["created_at"].strftime("%d.%m %H:%M")
            who = await _user_display(call.bot, item["actor_id"]) if item["actor_id"] is not None else "system"
            scope = f"chat:{item['scope_id']}" if item["scope_type"] == "chat" else "global"
            lines.append(f"{ts} | {item['title']} | {item['old']} → {item['new']} | by {who} | {scope}")
        await call.message.edit_text("\n".join(lines), reply_markup=_owner_nav_keyboard("own_home"))
        await call.answer()
        return

    if data == "own_reports":
        reports_chat = int(await get_setting("groups.reports"))
        logs_chat = int(await get_setting("groups.logs"))
        reports_name = await _chat_anchor(call.bot, reports_chat)
        logs_name = await _chat_anchor(call.bot, logs_chat)
        await call.message.edit_text(
            "📨 <b>Репорты и логи</b>\n"
            f"Репорты: {reports_name}\n"
            f"Логи: {logs_name}",
            reply_markup=_owner_reports_keyboard()
        )
        await call.answer()
        return

    if data == "own_quick":
        await call.message.edit_text("⚡ <b>Быстрые действия</b>", reply_markup=_owner_quick_keyboard())
        await call.answer()
        return

    if data == "own_chat_add":
        await call.message.edit_text(
            "🧭 <b>Подключить канал/группу на мониторинг</b>\n\n"
            "Чтобы подключить группу или канал, бот должен быть туда добавлен как <b>администратор</b>.\n"
            "1) Добавьте бота админом в нужный чат/канал.\n"
            "2) Нажмите «Обновить список чатов».\n"
            "3) Перейдите к выбору групп мониторинга.\n",
            reply_markup=_owner_monitor_intro_keyboard("own_chats")
        )
        await call.answer()
        return

    if data == "own_chat_disable":
        candidates = [c for c in await list_managed_chats(enabled_only=True)]
        buttons = [
            [InlineKeyboardButton(
                text=await _chat_button_title(call.bot, row.chat_id),
                callback_data=f"own_chat_disable_pick_{row.chat_id}"
            )]
            for row in candidates[:30]
        ]
        buttons.append([InlineKeyboardButton(text="⬅ Назад", callback_data="own_chats")])
        await call.message.edit_text(
            "Выберите чат, для которого нужно отключить мониторинг:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await call.answer()
        return

    if data.startswith("own_chat_disable_pick_"):
        chat_id = int(data.replace("own_chat_disable_pick_", ""))
        chat_label = await _chat_display(call.bot, chat_id)
        await call.message.edit_text(
            "Отключить мониторинг для чата:\n"
            f"{chat_label} ?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⛔ Отключить мониторинг", callback_data=f"own_chat_disable_confirm_{chat_id}")],
                [InlineKeyboardButton(text="⬅ Назад", callback_data="own_chat_disable")],
            ])
        )
        await call.answer()
        return

    if data.startswith("own_chat_disable_confirm_"):
        chat_id = int(data.replace("own_chat_disable_confirm_", ""))
        changed = await disable_chat(chat_id)
        await call.answer("Мониторинг отключён" if changed else "Чат не найден")
        await call.message.edit_text(
            "✅ Мониторинг чата отключён." if changed else "ℹ️ Чат не найден.",
            reply_markup=_owner_chats_keyboard()
        )
        return

    if data == "own_chat_select_active":
        chats = await list_managed_chats(enabled_only=True)
        buttons = []
        for row in chats[:30]:
            buttons.append([InlineKeyboardButton(text=await _chat_button_title(call.bot, row.chat_id), callback_data=f"own_active_{row.chat_id}")])
        buttons.append([InlineKeyboardButton(text="⬅ Назад", callback_data="own_chats")])
        await call.message.edit_text(
            "Выберите чат для настройки:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await call.answer()
        return

    if data.startswith("own_active_"):
        chat_id = int(data.split("_")[2])
        await _set_active_chat_id(call.from_user.id, chat_id)
        _set_scope(call.from_user.id, "chat")
        await call.message.edit_text(
            await _render_settings_categories_text(call.bot, chat_id),
            reply_markup=_panel_categories_keyboard()
        )
        await call.answer("Сохранено")
        return

    if data == "own_link_add":
        owner_dialog_state[call.from_user.id] = OwnerDialogState("link_add", {})
        await call.message.edit_text(
            "Введите два числа: <code>group_chat_id channel_chat_id</code>",
            reply_markup=_owner_nav_keyboard("own_links")
        )
        await call.answer()
        return

    if data == "own_link_rm":
        owner_dialog_state[call.from_user.id] = OwnerDialogState("link_rm", {})
        await call.message.edit_text(
            "Введите два числа: <code>group_chat_id channel_chat_id</code> для удаления связки",
            reply_markup=_owner_nav_keyboard("own_links")
        )
        await call.answer()
        return

    if data == "own_owner_add":
        owner_dialog_state[call.from_user.id] = OwnerDialogState("owner_add", {})
        await call.message.edit_text(
            "Введите <code>user_id</code> нового owner.",
            reply_markup=_owner_nav_keyboard("own_owners")
        )
        await call.answer()
        return

    if data == "own_owner_rm":
        owner_dialog_state[call.from_user.id] = OwnerDialogState("owner_rm", {})
        await call.message.edit_text(
            "Введите <code>user_id</code> owner для удаления.",
            reply_markup=_owner_nav_keyboard("own_owners")
        )
        await call.answer()
        return

    if data == "own_cfg_keys":
        await call.message.edit_text("Тех. список ключей убран из интерфейса.", reply_markup=_owner_settings_keyboard())
        await call.answer()
        return

    if data == "own_test_log":
        from utils import write_log
        await write_log(call.bot, "Тест лога из owner-меню", "test-owner")
        await call.answer("Отправлено в лог")
        return

    if data == "own_test_reports":
        reports_chat = int(await get_setting("groups.reports"))
        await call.bot.send_message(reports_chat, "Тест репорт-канала из owner-меню.")
        await call.answer("Отправлено в reports")
        return

    if data == "own_quick_broadcast":
        owner_dialog_state[call.from_user.id] = OwnerDialogState("quick_broadcast", {})
        await call.message.edit_text(
            "Введите текст для рассылки во все чаты.",
            reply_markup=_owner_nav_keyboard("own_quick")
        )
        await call.answer()
        return

    if data == "own_quick_automute_on":
        await set_setting("moderation.new_user_automute_enabled", True, actor_id=call.from_user.id)
        await call.answer("Автомьют включён")
        await call.message.edit_text(await _build_owner_home_text(), reply_markup=_owner_home_keyboard())
        return

    if data == "own_quick_automute_off":
        await set_setting("moderation.new_user_automute_enabled", False, actor_id=call.from_user.id)
        await call.answer("Автомьют выключен")
        await call.message.edit_text(await _build_owner_home_text(), reply_markup=_owner_home_keyboard())
        return

    if data == "own_quick_interval_60":
        await set_setting("moderation.message_min_interval_sec", 60, actor_id=call.from_user.id)
        await call.answer("Интервал = 60с")
        await call.message.edit_text(await _build_owner_home_text(), reply_markup=_owner_home_keyboard())
        return

    if data == "own_quick_interval_0":
        await set_setting("moderation.message_min_interval_sec", 0, actor_id=call.from_user.id)
        await call.answer("Интервал отключён")
        await call.message.edit_text(await _build_owner_home_text(), reply_markup=_owner_home_keyboard())
        return

    await call.answer("Неизвестное действие", show_alert=True)


@router.message(F.chat.type == "private", IsOwnerFilter(), F.text)
async def on_owner_dialog_input(message: Message) -> None:
    """Text input handler for owner panel flows."""
    if message.text.startswith("/") or message.text.startswith("!/"):
        return

    state = owner_dialog_state.get(message.from_user.id)
    if not state:
        return

    text = (message.text or "").strip()
    owner_dialog_state.pop(message.from_user.id, None)

    try:
        if state.action == "link_add":
            group_id_s, channel_id_s = text.split(maxsplit=1)
            await add_linked_channel(int(group_id_s), int(channel_id_s))
            await message.reply("✅ Связка добавлена.")
            return

        if state.action == "link_rm":
            group_id_s, channel_id_s = text.split(maxsplit=1)
            changed = await remove_linked_channel(int(group_id_s), int(channel_id_s))
            await message.reply("✅ Связка удалена." if changed else "ℹ️ Связка не найдена.")
            return

        if state.action == "owner_add":
            owner_id = int(text)
            changed = await add_owner(owner_id, actor_id=message.from_user.id)
            await message.reply("✅ Owner добавлен." if changed else "ℹ️ Уже owner.")
            return

        if state.action == "owner_rm":
            owner_id = int(text)
            changed = await remove_owner(owner_id)
            await message.reply("✅ Owner удалён." if changed else "ℹ️ Owner не найден.")
            return

        if state.action == "cfg_set_smart":
            key = state.payload["key"]
            chat_id = state.payload.get("chat_id")
            if not chat_id:
                await message.reply("Сначала выберите чат для настройки.")
                return
            meta = get_setting_meta(key)
            if meta.input_mode in ("seconds", "number"):
                value = parse_setting_input(key, str(int(text)))
            else:
                value = parse_setting_input(key, text)
            applied = await set_setting(key, value, actor_id=message.from_user.id, chat_id=chat_id)
            await message.reply(
                f"{await _settings_chat_header(message.bot, chat_id)}\n\n"
                f"✅ {meta.title}: <code>{format_setting_value(key, applied)}</code>\n"
                "Параметр обновлён.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="⬅ Вернуться к настройкам", callback_data="own_cfg_categories")],
                    [InlineKeyboardButton(text="🏠 Домой", callback_data="own_home")],
                ])
            )
            return

        if state.action == "quick_broadcast":
            sent = 0
            failed = 0
            for chat_id in await get_main_chat_ids():
                try:
                    await message.bot.send_message(chat_id, text)
                    sent += 1
                except Exception:
                    failed += 1
            await message.reply(f"✅ Рассылка завершена.\nУспешно: {sent}\nОшибок: {failed}")
            return
    except ValueError as e:
        await message.reply(f"❌ Ошибка формата: {e}")
        return
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")
        return


@router.message(
    F.chat.type == "private",
    IsOwnerFilter(),
    Command("owners", prefix="!/")
)
async def cmd_owners(message: Message) -> None:
    """Manage owners: !owners list|add <id>|del <id>."""
    parts = message.text.split()
    if len(parts) == 1 or parts[1] == "list":
        owner_ids = await list_owner_ids()
        lines = [f"- {await _user_display(message.bot, oid)}" for oid in owner_ids]
        await message.reply(
            "👑 <b>Owners:</b>\n" + "\n".join(lines)
        )
        return

    if len(parts) < 3:
        await message.reply("Использование: !owners list | !owners add <user_id> | !owners del <user_id>")
        return

    action = parts[1].lower()
    try:
        user_id = int(parts[2])
    except ValueError:
        await message.reply("user_id должен быть числом.")
        return

    if action == "add":
        changed = await add_owner(user_id, actor_id=message.from_user.id)
        await message.reply("✅ Добавлен owner." if changed else "ℹ️ Уже owner.")
    elif action in ("del", "rm", "remove"):
        try:
            changed = await remove_owner(user_id)
            await message.reply("✅ Owner удалён." if changed else "ℹ️ Owner не найден.")
        except ValueError as e:
            await message.reply(f"❌ {e}")
    else:
        await message.reply("Неизвестное действие. Использование: list|add|del")


@router.message(
    F.chat.type == "private",
    IsOwnerFilter(),
    Command("chats", prefix="!/")
)
async def cmd_chats(message: Message) -> None:
    """List managed chats."""
    chats = await list_managed_chats(enabled_only=False)
    if not chats:
        await message.reply("Список чатов пуст.")
        return

    lines = ["🧩 <b>Managed chats:</b>"]
    for row in chats:
        mon = "MON:ON" if row.is_enabled else "MON:OFF"
        role = f"BOT:{row.bot_status}"
        lines.append(f"- {await _chat_display(message.bot, row.chat_id)} [{mon}] [{role}]")
    await message.reply("\n".join(lines))


@router.message(
    F.chat.type == "private",
    IsOwnerFilter(),
    Command("chat_add", prefix="!/")
)
async def cmd_chat_add(message: Message) -> None:
    """Add/enable managed chat: !chat_add <chat_id>."""
    parts = message.text.split()
    if len(parts) < 2:
        await message.reply("Использование: !chat_add <chat_id>")
        return
    try:
        chat_id = int(parts[1])
    except ValueError:
        await message.reply("chat_id должен быть числом.")
        return

    title = None
    chat_type = "supergroup"
    try:
        chat = await message.bot.get_chat(chat_id)
        title = chat.title or chat.full_name
        chat_type = chat.type
    except Exception:
        pass

    await register_chat(chat_id, chat_type=chat_type, title=title, bot_status="administrator", is_enabled=True)
    await message.reply(f"✅ Чат добавлен/включён: {await _chat_display(message.bot, chat_id)}")


@router.message(
    F.chat.type == "private",
    IsOwnerFilter(),
    Command("chat_rm", prefix="!/")
)
async def cmd_chat_rm(message: Message) -> None:
    """Disable managed chat: !chat_rm <chat_id>."""
    parts = message.text.split()
    if len(parts) < 2:
        await message.reply("Использование: !chat_rm <chat_id>")
        return
    try:
        chat_id = int(parts[1])
    except ValueError:
        await message.reply("chat_id должен быть числом.")
        return

    changed = await disable_chat(chat_id)
    await message.reply("✅ Чат отключён." if changed else "ℹ️ Чат не найден.")


@router.message(
    F.chat.type == "private",
    IsOwnerFilter(),
    Command("links", prefix="!/")
)
async def cmd_links(message: Message) -> None:
    """List linked channels."""
    rows = await list_linked_channels()
    if not rows:
        await message.reply("Связанных каналов пока нет.")
        return
    lines = ["🔗 <b>Linked channels:</b>"]
    for row in rows:
        lines.append(
            f"- group {await _chat_display(message.bot, row.group_chat_id)} -> "
            f"channel {await _chat_display(message.bot, row.channel_chat_id)}"
        )
    await message.reply("\n".join(lines))


@router.message(
    F.chat.type == "private",
    IsOwnerFilter(),
    Command("link_add", prefix="!/")
)
async def cmd_link_add(message: Message) -> None:
    """Add linked channel: !link_add <group_id> <channel_id>."""
    parts = message.text.split()
    if len(parts) < 3:
        await message.reply("Использование: !link_add <group_id> <channel_id>")
        return
    try:
        group_id = int(parts[1])
        channel_id = int(parts[2])
    except ValueError:
        await message.reply("group_id и channel_id должны быть числами.")
        return

    await add_linked_channel(group_id, channel_id)
    await message.reply("✅ Связка добавлена.")


@router.message(
    F.chat.type == "private",
    IsOwnerFilter(),
    Command("link_rm", prefix="!/")
)
async def cmd_link_rm(message: Message) -> None:
    """Remove linked channel: !link_rm <group_id> <channel_id>."""
    parts = message.text.split()
    if len(parts) < 3:
        await message.reply("Использование: !link_rm <group_id> <channel_id>")
        return
    try:
        group_id = int(parts[1])
        channel_id = int(parts[2])
    except ValueError:
        await message.reply("group_id и channel_id должны быть числами.")
        return

    changed = await remove_linked_channel(group_id, channel_id)
    await message.reply("✅ Связка удалена." if changed else "ℹ️ Связка не найдена.")


@router.message(
    F.chat.type == "private",
    IsOwnerFilter(),
    Command("cfgkeys", prefix="!/")
)
async def cmd_cfg_keys(message: Message) -> None:
    """List available runtime setting keys."""
    keys = list_setting_keys()
    await message.reply("🛠 <b>Runtime keys:</b>\n" + "\n".join(f"- <code>{k}</code>" for k in keys))


@router.message(
    F.chat.type == "private",
    IsOwnerFilter(),
    Command("getcfg", prefix="!/")
)
async def cmd_get_cfg(message: Message) -> None:
    """Get setting value: !getcfg <key> [chat_id]."""
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.reply("Использование: !getcfg <key> [chat_id]")
        return

    key = parts[1].strip()
    chat_id = None
    if len(parts) == 3:
        try:
            chat_id = int(parts[2].strip())
        except ValueError:
            await message.reply("chat_id должен быть числом.")
            return

    try:
        value = await get_setting(key, chat_id=chat_id)
    except Exception as e:
        await message.reply(f"❌ {e}")
        return

    scope = f"chat={chat_id}" if chat_id is not None else "global"
    await message.reply(f"✅ <code>{key}</code> ({scope}) = <code>{value}</code>")


@router.message(
    F.chat.type == "private",
    IsOwnerFilter(),
    Command("setcfg", prefix="!/")
)
async def cmd_set_cfg(message: Message) -> None:
    """Set setting value: !setcfg <key> <value> [chat_id]."""
    parts = message.text.split()
    if len(parts) < 3:
        await message.reply("Использование: !setcfg <key> <value> [chat_id]")
        return

    key = parts[1]
    raw_value = parts[2]
    chat_id = None
    if len(parts) > 3:
        try:
            chat_id = int(parts[3])
        except ValueError:
            await message.reply("chat_id должен быть числом.")
            return

    try:
        value = parse_setting_input(key, raw_value)
        applied = await set_setting(key, value, actor_id=message.from_user.id, chat_id=chat_id)
    except Exception as e:
        await message.reply(f"❌ {e}")
        return

    scope = f"chat={chat_id}" if chat_id is not None else "global"
    await message.reply(f"✅ Установлено: <code>{key}</code> ({scope}) = <code>{applied}</code>")


@router.message(
    F.chat.type == "private",
    IsOwnerFilter(),
    Command("delcfg", prefix="!/")
)
async def cmd_del_cfg(message: Message) -> None:
    """Reset setting to fallback/default: !delcfg <key> [chat_id]."""
    parts = message.text.split()
    if len(parts) < 2:
        await message.reply("Использование: !delcfg <key> [chat_id]")
        return
    key = parts[1]
    chat_id = None
    if len(parts) > 2:
        try:
            chat_id = int(parts[2])
        except ValueError:
            await message.reply("chat_id должен быть числом.")
            return
    try:
        await reset_setting(key, actor_id=message.from_user.id, chat_id=chat_id)
    except Exception as e:
        await message.reply(f"❌ {e}")
        return

    scope = f"chat={chat_id}" if chat_id is not None else "global"
    await message.reply(f"✅ Сброшено: <code>{key}</code> ({scope})")


@router.message(
    IsOwnerFilter(),
    Command("msg", prefix="!/")
)
async def cmd_message_from_bot(message: Message) -> None:
    """
    Send a message from bot (owner only).
    
    Usage:
        !msg <text> - Shows keyboard to select target chat
    """
    _cleanup_old_messages()
    
    text = remove_prefix(message.text, "!msg").strip()
    
    if not text:
        await message.reply(
            "<b>Использование:</b>\n"
            "<code>!msg текст сообщения</code>\n\n"
            "После ввода команды появится меню выбора чата."
        )
        return
    
    # generate unique ID
    msg_id = uuid.uuid4().hex[:8]
    pending_messages[msg_id] = (text, datetime.now())
    
    # build keyboard
    keyboard = await _build_chat_keyboard(message.bot, msg_id)
    
    await message.reply(
        f"<b>Сообщение:</b>\n<i>{text[:500]}{'...' if len(text) > 500 else ''}</i>\n\n"
        f"Выберите куда отправить:",
        reply_markup=keyboard
    )


@router.message(
    IsOwnerFilter(),
    Command("log", prefix="!/")
)
async def cmd_write_log_bot(message: Message) -> None:
    """Write a test log message (owner only)."""
    from utils import write_log
    text = remove_prefix(message.text, "!log ").strip()
    if text:
        await write_log(message.bot, text, "test")


@router.message(
    IsOwnerFilter(),
    Command("reload", prefix="!/")
)
async def cmd_reload_announcements(message: Message) -> None:
    """Reload announcements from file (owner only)."""
    from services.announcements import reload_announcements
    count = reload_announcements()
    await message.reply(f"✅ Перезагружено {count} объявлений.")


@router.message(
    IsOwnerFilter(),
    Command("chatid", prefix="!/")
)
async def cmd_chat_id(message: Message) -> None:
    """Get current chat ID (owner only)."""
    chat = message.chat
    chat_type = chat.type
    chat_title = chat.title or chat.full_name or "Private"
    
    info = (
        f"<b>Chat ID:</b> <code>{chat.id}</code>\n"
        f"<b>Type:</b> {chat_type}\n"
        f"<b>Title:</b> {chat_title}"
    )
    
    # print to console
    print(f"\n{'='*40}")
    print(f"CHAT ID: {chat.id}")
    print(f"Type: {chat_type}")
    print(f"Title: {chat_title}")
    print(f"{'='*40}\n")
    
    await message.reply(info)


@router.message(
    InMainGroups(),
    IsAdminFilter(),
    Command("ping", prefix="!")
)
async def cmd_ping_bot(message: Message) -> None:
    """Check if bot is alive and show system stats."""
    ram = psutil.virtual_memory()
    cpu_freq = psutil.cpu_freq().current if psutil.cpu_freq() else 0

    reply = f"<b>{random.choice(['👊 Самурай на месте!', '🫰 Нужно больше золота', '🫡 Тута я, бож :3', '✊ Железо говн@, но я держусь!'])}</b>\n\n"

    # cpu
    reply += "<b>CPU:</b> <i>{} ядер, {:.0f} MHz, загрузка {}%</i>\n".format(
        psutil.cpu_count(logical=True),
        cpu_freq,
        psutil.cpu_percent(interval=1)
    )

    # ram
    reply += "<b>RAM:</b> <i>{} МБ / {} МБ ({}%)</i>\n".format(
        ram.used // (1024 ** 2),
        ram.total // (1024 ** 2),
        ram.percent
    )

    # gpu
    reply += "<b>GPU:</b> <i>N/A</i>\n"

    # disk
    disk = psutil.disk_usage('/')
    disk_total_gb = disk.total / (1024 ** 3)
    disk_used_gb = disk.used / (1024 ** 3)

    reply += "<b>SSD:</b> <i>{:.2f} ГБ из {:.2f} ГБ использовано ({}% занято)</i>\n".format(
        disk_used_gb,
        disk_total_gb,
        int(disk.percent)
    )

    # location
    reply += "<b>Расположение сервера:</b> <i>Марс</i>\n"

    # version
    reply += f"\n<b>Версия бота:</b> <i>{config.bot.version} codename «<b>{config.bot.version_codename}</b>»</i>"

    await message.reply(reply)


@router.message(
    InMainGroups(),
    IsAdminFilter(),
    Command("prof", "мат", prefix="!")
)
async def cmd_profanity_check(message: Message) -> None:
    """Check text for profanity (admin only)."""
    text = remove_prefix(message.text, "!prof ").strip()
    if not text:
        text = remove_prefix(message.text, "!мат ").strip()
    
    if not text:
        await message.reply("Укажите текст для проверки после команды.")
        return

    # check russian
    is_profanity_ru, word_ru, line_info_ru = check_for_profanity(text, "ru")
    
    # check english
    is_profanity_en, word_en, line_info_en = check_for_profanity(text, "en")

    if is_profanity_ru or is_profanity_en:
        word = word_ru if is_profanity_ru else word_en
        pattern = line_info_ru[5][0] if is_profanity_ru else line_info_en[5][0]
        lang = "ru" if is_profanity_ru else "en"

        log_msg = f"❌ Profanity detected.\n\n"
        log_msg += text.replace(word, f'<u><b>{word}</b></u>')
        log_msg += f"\nПаттерн: {pattern}"
        log_msg += f"\nЯзык: {lang}"

        await message.reply(log_msg)
    else:
        await message.reply("✅ No profanity detected.")


@router.message(
    F.chat.type == "private",
    IsOwnerFilter(),
    Command("prof", "мат", prefix="!")
)
async def cmd_profanity_check_private(message: Message) -> None:
    """Check text for profanity in private chat (owner only)."""
    text = remove_prefix(message.text, "!prof ").strip()
    if not text:
        text = remove_prefix(message.text, "!мат ").strip()

    if not text:
        await message.reply("Укажите текст для проверки после команды.")
        return

    # check russian
    is_profanity_ru, word_ru, line_info_ru = check_for_profanity(text, "ru")

    # check english
    is_profanity_en, word_en, line_info_en = check_for_profanity(text, "en")

    if is_profanity_ru or is_profanity_en:
        word = word_ru if is_profanity_ru else word_en
        pattern = line_info_ru[5][0] if is_profanity_ru else line_info_en[5][0]
        lang = "ru" if is_profanity_ru else "en"

        log_msg = f"❌ Profanity detected.\n\n"
        log_msg += text.replace(word, f'<u><b>{word}</b></u>')
        log_msg += f"\nПаттерн: {pattern}"
        log_msg += f"\nЯзык: {lang}"

        await message.reply(log_msg)
    else:
        await message.reply("✅ No profanity detected.")


@router.message(
    IsOwnerFilter(),
    Command("nsfw", prefix="!"),
    F.photo
)
async def cmd_nsfw_test(message: Message) -> None:
    """
    Test NSFW detection on an attached photo (owner only).

    Usage: attach a photo and add !nsfw as caption
    """
    photo = message.photo[-1]

    img_file = await message.bot.get_file(photo.file_id)
    file_bytes = await message.bot.download_file(img_file.file_path)
    image = Image.open(io.BytesIO(file_bytes.getvalue())).convert("RGB")

    prediction = await asyncio.to_thread(nsfw_predict, np.asarray(image))

    # lazy import to avoid circular dep (personal_actions loads before group_events)
    from handlers.group_events import is_nsfw_detected
    verdict = await is_nsfw_detected(prediction)

    lines = ["🔞 <b>NSFW Test Results:</b>\n"]
    for label, score in prediction.items():
        bar = "█" * int(float(score) * 20)
        lines.append(f"  <b>{label}:</b> {score} {bar}")

    lines.append(f"\n<b>Verdict:</b> {'🚫 NSFW' if verdict else '✅ Safe'}")

    await message.reply("\n".join(lines))
