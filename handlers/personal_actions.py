"""
Personal/owner action handlers (ping, profanity check, message from bot).
"""
import random
import sys

import psutil
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from config import config
from filters import IsOwnerFilter, IsAdminFilter, InMainGroups
from services.profanity import check_for_profanity
from utils import remove_prefix, MemberStatus

sys.path.append("./libs")

router = Router(name="personal_actions")


@router.message(
    IsOwnerFilter(),
    Command("msg", prefix="!/")
)
async def cmd_message_from_bot(message: Message) -> None:
    """Send a message to all main groups from bot (owner only)."""
    text = remove_prefix(message.text, "!msg ").strip()
    if text:
        # Send to all configured main groups
        for group_id in config.groups.main:
            try:
                await message.bot.send_message(group_id, text)
            except Exception:
                pass


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
