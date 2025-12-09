"""
Personal/owner action handlers (ping, profanity check, message from bot).
"""
import random
import sys
import uuid
from datetime import datetime, timedelta

import psutil
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import config
from filters import IsOwnerFilter, IsAdminFilter, InMainGroups
from services.profanity import check_for_profanity
from utils import remove_prefix, MemberStatus

sys.path.append("./libs")

router = Router(name="personal_actions")

# Temporary storage for pending messages (auto-cleanup after 5 minutes)
_pending_messages: dict[str, tuple[str, datetime]] = {}


def _cleanup_old_messages() -> None:
    """Remove messages older than 5 minutes."""
    now = datetime.now()
    expired = [k for k, (_, ts) in _pending_messages.items() if now - ts > timedelta(minutes=5)]
    for k in expired:
        del _pending_messages[k]


async def _build_chat_keyboard(bot, msg_id: str) -> InlineKeyboardMarkup:
    """Build inline keyboard with chat names."""
    buttons = []
    
    for chat_id in config.groups.main:
        try:
            chat = await bot.get_chat(chat_id)
            chat_name = chat.title or f"Chat {chat_id}"
        except Exception:
            chat_name = f"Chat {chat_id}"
        
        buttons.append([InlineKeyboardButton(
            text=f"📤 {chat_name}",
            callback_data=f"msg_{msg_id}_{chat_id}"
        )])
    
    # Add "Send to all" button
    buttons.append([InlineKeyboardButton(
        text="📢 Отправить во все чаты",
        callback_data=f"msg_{msg_id}_all"
    )])
    
    # Add cancel button
    buttons.append([InlineKeyboardButton(
        text="❌ Отмена",
        callback_data=f"msg_{msg_id}_cancel"
    )])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


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
    
    # Generate unique ID and store message
    msg_id = uuid.uuid4().hex[:8]
    _pending_messages[msg_id] = (text, datetime.now())
    
    # Build keyboard
    keyboard = await _build_chat_keyboard(message.bot, msg_id)
    
    await message.reply(
        f"<b>Сообщение:</b>\n<i>{text[:500]}{'...' if len(text) > 500 else ''}</i>\n\n"
        f"Выберите куда отправить:",
        reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("msg_"))
async def callback_msg_send(call: CallbackQuery) -> None:
    """Handle message send callbacks."""
    # Verify owner
    if call.from_user.id not in config.bot.owner_ids:
        await call.answer("⛔ Только для владельца", show_alert=True)
        return
    
    parts = call.data.split("_")
    if len(parts) < 3:
        await call.answer("❌ Ошибка данных", show_alert=True)
        return
    
    msg_id = parts[1]
    target = "_".join(parts[2:])  # Handle negative chat IDs like -100123
    
    # Get stored message
    if msg_id not in _pending_messages:
        await call.message.edit_text("❌ Сообщение устарело. Отправьте команду заново.")
        await call.answer()
        return
    
    text, _ = _pending_messages[msg_id]
    
    if target == "cancel":
        del _pending_messages[msg_id]
        await call.message.edit_text("❌ Отменено.")
        await call.answer()
        return
    
    if target == "all":
        # Send to all chats
        sent = 0
        failed = 0
        for chat_id in config.groups.main:
            try:
                await call.bot.send_message(chat_id, text)
                sent += 1
            except Exception:
                failed += 1
        
        del _pending_messages[msg_id]
        await call.message.edit_text(
            f"✅ <b>Отправлено во все чаты</b>\n\n"
            f"Успешно: {sent}\n"
            f"Ошибок: {failed}"
        )
        await call.answer("Отправлено!")
    else:
        # Send to specific chat
        try:
            chat_id = int(target)
            await call.bot.send_message(chat_id, text)
            
            # Get chat name for confirmation
            try:
                chat = await call.bot.get_chat(chat_id)
                chat_name = chat.title or f"Chat {chat_id}"
            except Exception:
                chat_name = f"Chat {chat_id}"
            
            del _pending_messages[msg_id]
            await call.message.edit_text(f"✅ <b>Отправлено в:</b> {chat_name}")
            await call.answer("Отправлено!")
        except ValueError:
            await call.answer("❌ Неверный ID чата", show_alert=True)
        except Exception as e:
            await call.answer(f"❌ Ошибка: {str(e)[:100]}", show_alert=True)


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
    InMainGroups(),
    IsAdminFilter(),
    Command("ping", prefix="!")
)
async def cmd_ping_bot(message: Message) -> None:
    """Check if bot is alive and show system stats."""
    # Verify admin in current group
    user = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
    if user.status not in MemberStatus.admin_statuses():
        return

    ram = psutil.virtual_memory()
    cpu_freq = psutil.cpu_freq().current if psutil.cpu_freq() else 0

    reply = f"<b>{random.choice(['👊 Самурай на месте!', '🫰 Нужно больше золота', '🫡 Тута я, бож :3', '✊ Железо говн@, но я держусь!'])}</b>\n\n"

    # CPU
    reply += "<b>CPU:</b> <i>{} ядер, {:.0f} MHz, загрузка {}%</i>\n".format(
        psutil.cpu_count(logical=True),
        cpu_freq,
        psutil.cpu_percent(interval=1)
    )

    # RAM
    reply += "<b>RAM:</b> <i>{} МБ / {} МБ ({}%)</i>\n".format(
        ram.used // (1024 ** 2),
        ram.total // (1024 ** 2),
        ram.percent
    )

    # GPU
    reply += "<b>GPU:</b> <i>N/A</i>\n"

    # Disk
    disk = psutil.disk_usage('/')
    disk_total_gb = disk.total / (1024 ** 3)
    disk_used_gb = disk.used / (1024 ** 3)

    reply += "<b>SSD:</b> <i>{:.2f} ГБ из {:.2f} ГБ использовано ({}% занято)</i>\n".format(
        disk_used_gb,
        disk_total_gb,
        int(disk.percent)
    )

    # Location
    reply += "<b>Расположение сервера:</b> <i>Марс</i>\n"

    # Version
    reply += f"\n<b>Версия бота:</b> <i>{config.bot.version} codename «<b>{config.bot.version_codename}</b>»</i>"

    await message.reply(reply)


@router.message(
    InMainGroups(),
    IsAdminFilter(),
    Command("prof", "мат", prefix="!")
)
async def cmd_profanity_check(message: Message) -> None:
    """Check text for profanity (admin only)."""
    # Verify admin in current group
    user = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
    if user.status not in MemberStatus.admin_statuses():
        return

    text = remove_prefix(message.text, "!prof ").strip()
    if not text:
        text = remove_prefix(message.text, "!мат ").strip()
    
    if not text:
        await message.reply("Укажите текст для проверки после команды.")
        return

    # Check Russian
    is_profanity_ru, word_ru, line_info_ru = check_for_profanity(text, "ru")
    
    # Check English
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

    # Check Russian
    is_profanity_ru, word_ru, line_info_ru = check_for_profanity(text, "ru")
    
    # Check English
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
