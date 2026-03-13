"""
Personal/owner action handlers (ping, profanity check, message from bot, NSFW test).
"""
import asyncio
import io
import random
import uuid
from datetime import datetime, timedelta

import numpy as np
import psutil
from PIL import Image
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from config import config
from filters import IsOwnerFilter, IsAdminFilter, InMainGroups
from services.chat_registry import (
    get_main_chat_ids,
    list_managed_chats,
    register_chat,
    disable_chat,
    add_linked_channel,
    remove_linked_channel,
    list_linked_channels,
)
from services.owners import list_owner_ids, add_owner, remove_owner
from services.runtime_settings import (
    get_setting,
    set_setting,
    reset_setting,
    list_setting_keys,
    parse_setting_input,
)
from services.nsfw import classify_explicit_content as nsfw_predict
from services.profanity import check_for_profanity
from utils import remove_prefix

router = Router(name="personal_actions")

# temp storage for pending msgs (auto-cleanup after 5 minutes)
# used by callbacks.py
pending_messages: dict[str, tuple[str, datetime]] = {}
MAX_PENDING_MESSAGES = 50


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
        await message.reply(
            "👑 <b>Owners:</b>\n" + "\n".join(f"- <code>{oid}</code>" for oid in owner_ids)
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
        state = "ON" if row.is_enabled else "OFF"
        lines.append(f"- <code>{row.chat_id}</code> [{state}] {row.title or ''}".strip())
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
    await message.reply(f"✅ Чат <code>{chat_id}</code> добавлен/включён.")


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
        lines.append(f"- group <code>{row.group_chat_id}</code> -> channel <code>{row.channel_chat_id}</code>")
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
