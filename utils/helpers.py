"""
Utility helper functions.
"""
import datetime
from typing import Optional

import psutil
from aiogram.types import Message
from aiogram.enums import ContentType

from config import config
from utils.localization import get_string


def get_message_text(message: Message) -> Optional[str]:
    """
    Extract text content from a message.
    
    Handles both regular text messages and captions on media.
    
    Args:
        message: The message to extract text from
        
    Returns:
        The message text/caption or None if no text content
    """
    if message.content_type == ContentType.TEXT:
        return message.text
    elif message.content_type in (
        ContentType.PHOTO, 
        ContentType.DOCUMENT, 
        ContentType.VIDEO,
        ContentType.ANIMATION,
        ContentType.AUDIO,
        ContentType.VOICE,
        ContentType.VIDEO_NOTE
    ):
        return message.caption
    return None


def user_mention(from_user) -> str:
    """Generate user mention HTML."""
    _s = from_user.full_name

    if from_user.full_name != from_user.mention_html():
        _s += " (" + from_user.mention_html() + ")"
    else:
        _s += f' (<a href="{from_user.url}">id{from_user.id}</a>)'

    return _s


def generate_log_message(
    message: str,
    log_type: str = "default",
    chat_title: Optional[str] = None
) -> str:
    """
    Generate formatted log message.
    
    Args:
        message: Log message content
        log_type: Type of log (e.g., "ban", "mute", "spam")
        chat_title: Name of the chat (for multi-group support)
    """
    now = datetime.datetime.now()
    current_time = now.strftime("%H:%M:%S")

    log_message = f"🕥 <i>{current_time}</i> "
    
    if chat_title:
        log_message += f"[<b>{chat_title}</b>] "
    
    log_message += f"<b>[{log_type.upper()}]</b> "
    log_message += message

    return log_message


async def write_log(
    bot,
    message: str,
    log_type: str = "default",
    chat_title: Optional[str] = None
):
    """
    Write log message to logs channel.
    
    Args:
        bot: Bot instance
        message: Log message content
        log_type: Type of log
        chat_title: Name of the chat (for multi-group support)
    """
    return await bot.send_message(
        config.groups.logs,
        generate_log_message(message, log_type, chat_title)
    )


def get_restriction_time(string: str) -> Optional[int]:
    """
    Get user restriction time in seconds.

    Args:
        string: Time string (e.g., "2h", "1d", "30m")

    Returns:
        Number of seconds or None if invalid format
    """
    if len(string) < 2:
        return None

    letter = string[-1]
    try:
        number = int(string[:-1])
    except (TypeError, ValueError):
        return None
    else:
        if letter == "m":
            return 60 * number
        elif letter == "h":
            return 3600 * number
        elif letter == "d":
            return 86400 * number
        else:
            return None


def get_report_comment(
    message_date: datetime.datetime,
    message_id: int,
    chat_id: int,
    report_message: Optional[str] = None,
    chat_title: Optional[str] = None
) -> str:
    """
    Generate report message for admins.
    
    Args:
        message_date: Date of the reported message
        message_id: ID of the reported message
        chat_id: ID of the chat where message was sent
        report_message: Optional note from reporter
        chat_title: Name of the chat (for multi-group support)
    """
    # Build header with chat name if provided
    header = ""
    if chat_title:
        header = f"🟢 <b>{chat_title}</b>\n\n"
    
    # Pass variables directly to get_string for Fluent interpolation
    msg = header + get_string(
        "report_message",
        date=message_date.strftime(get_string("report_date_format")),
        chat_id=get_url_chat_id(chat_id),
        msg_id=message_id
    )

    if report_message:
        msg += get_string("report_note", note=report_message)
    return msg


def get_url_chat_id(chat_id: int) -> int:
    """
    Convert chat_id for t.me links.

    This transforms the chat_id to work with https://t.me/c/{chat_id}/{msg_id} links.
    """
    return abs(chat_id + 1_000_000_000_000)


def remove_prefix(text: str, prefix: str) -> str:
    """Remove prefix from text if present."""
    if text.startswith(prefix):
        return text[len(prefix):]
    return text


def get_cpu_freq():
    """Get CPU frequency."""
    try:
        freq = psutil.cpu_freq()
        return freq.max if freq and freq.max > 0 else "N/A"
    except Exception:
        return "N/A"
