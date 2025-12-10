"""
Scheduled announcements service.

Loads announcements from locales/<lang>/announcements.ftl files.
Supports per-group filtering via @groups directive.
Persists last-sent timestamps to avoid re-sending after restart.
"""
import asyncio
import json
import logging
import re
import time
from pathlib import Path

from config import config

logger = logging.getLogger(__name__)

# Store bot reference globally for scheduler
_bot = None
_announcements: list[dict] = []

# File to store last-sent timestamps
TIMESTAMPS_FILE = Path("data/announcement_timestamps.json")


def _load_timestamps() -> dict[str, float]:
    """Load last-sent timestamps from file."""
    if not TIMESTAMPS_FILE.exists():
        return {}
    
    try:
        with open(TIMESTAMPS_FILE, 'r') as f:
            data = json.load(f)
            logger.info(f"Loaded {len(data)} announcement timestamps")
            return data
    except Exception as e:
        logger.warning(f"Failed to load timestamps: {e}")
        return {}


def _save_timestamps(timestamps: dict[str, float]) -> None:
    """Save last-sent timestamps to file."""
    try:
        TIMESTAMPS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(TIMESTAMPS_FILE, 'w') as f:
            json.dump(timestamps, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save timestamps: {e}")


def load_announcements(locale: str = "ru") -> list[dict]:
    """
    Load announcements from .ftl file.
    
    Format in .ftl:
        announcement-N =
            Message text (multiline)
            @every: 3600
            @groups: -100123, -100456  (optional)
    """
    announcements = []
    
    ftl_path = Path(f"locales/{locale}/announcements.ftl")
    if not ftl_path.exists():
        logger.warning(f"Announcements file not found: {ftl_path}")
        return announcements
    
    content = ftl_path.read_text(encoding="utf-8")
    
    # Parse announcement blocks
    # Match: announcement-N = followed by indented content
    pattern = r'^announcement-\d+\s*=\s*\n((?:[ \t]+.+\n?)+)'
    
    for match in re.finditer(pattern, content, re.MULTILINE):
        block = match.group(1)
        lines = block.split('\n')
        
        message_lines = []
        every = 3600  # Default 1 hour
        groups = None
        
        for line in lines:
            stripped = line.strip()
            
            if stripped.startswith('@every:'):
                try:
                    every = int(stripped.replace('@every:', '').strip())
                except ValueError:
                    logger.warning(f"Invalid @every value: {stripped}")
            elif stripped.startswith('@groups:'):
                try:
                    groups_str = stripped.replace('@groups:', '').strip()
                    groups = [int(g.strip()) for g in groups_str.split(',') if g.strip()]
                except ValueError:
                    logger.warning(f"Invalid @groups value: {stripped}")
            elif stripped and not stripped.startswith('#'):
                # Regular message line (preserve original indentation for multiline)
                # Remove only the base indentation (4 spaces typically)
                message_lines.append(line.lstrip())
        
        if message_lines:
            message = '\n'.join(message_lines).strip()
            announcement = {
                'message': message,
                'every': every,
            }
            if groups:
                announcement['groups'] = groups
            announcements.append(announcement)
            logger.debug(f"Loaded announcement: {message[:50]}... (every={every}s)")
    
    logger.info(f"Loaded {len(announcements)} announcements from {ftl_path}")
    return announcements


async def send_announcement(message: str, groups: list[int] | None = None) -> None:
    """
    Send announcement to specified groups or all main groups.
    
    Args:
        message: The message text to send
        groups: List of group IDs to send to, or None for all main groups
    """
    if _bot is None:
        logger.warning("Bot not initialized, skipping announcement")
        return
    
    target_groups = groups if groups else config.groups.main
    
    for group_id in target_groups:
        # Skip if group not in main groups (safety check)
        if group_id not in config.groups.main:
            logger.warning(f"Group {group_id} not in main groups, skipping")
            continue
            
        try:
            await _bot.send_message(group_id, message)
            logger.debug(f"Announcement sent to {group_id}")
        except Exception as e:
            logger.error(f"Failed to send announcement to {group_id}: {e}")


async def run_scheduler() -> None:
    """Run the announcement scheduler loop."""
    global _bot, _announcements
    
    # Wait for bot to be set
    while _bot is None:
        await asyncio.sleep(1)
    
    # Load announcements
    _announcements = load_announcements(config.locale.default)
    
    if not _announcements:
        logger.warning("No announcements loaded, scheduler idle")
        return
    
    logger.info(f"Scheduler started with {len(_announcements)} announcements")
    
    # Load persisted timestamps (uses wall-clock time for persistence)
    last_sent = _load_timestamps()
    
    # For new announcements, set their timestamp to now (wait full interval)
    current_time = time.time()
    for i in range(len(_announcements)):
        key = str(i)
        if key not in last_sent:
            last_sent[key] = current_time
            logger.debug(f"New announcement #{i+1} - will send after interval")
    
    _save_timestamps(last_sent)
    logger.info("Announcements initialized with persistent timestamps")
    
    while True:
        try:
            current_time = time.time()
            
            for i, announcement in enumerate(_announcements):
                key = str(i)
                interval = announcement['every']
                message = announcement['message']
                groups = announcement.get('groups')
                
                # Check if it's time to send
                time_since_last = current_time - last_sent.get(key, 0)
                if time_since_last >= interval:
                    await send_announcement(message, groups)
                    last_sent[key] = current_time
                    _save_timestamps(last_sent)
                    logger.info(f"Announcement #{i+1} sent (interval: {interval}s)")
            
            await asyncio.sleep(10)  # Check every 10 seconds
            
        except asyncio.CancelledError:
            logger.info("Scheduler cancelled")
            raise
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
            await asyncio.sleep(30)


def set_bot(bot) -> None:
    """Set the bot instance for announcements."""
    global _bot
    _bot = bot
    logger.info("Bot set for announcements")


def reload_announcements(locale: str = None) -> int:
    """Reload announcements from file. Returns count loaded."""
    global _announcements
    _announcements = load_announcements(locale or config.locale.default)
    return len(_announcements)
