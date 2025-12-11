"""
Scheduled announcements service.

Loads announcements from locales/<lang>/announcements.ftl files.
Supports per-group filtering via @groups directive.
Supports message references via @message directive.
Supports interval ranges via @every: min-max directive.
Persists last-sent timestamps to avoid re-sending after restart.
"""
import asyncio
import json
import logging
import random
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


def _migrate_timestamps(timestamps: dict[str, float], announcements: list[dict]) -> dict[str, float]:
    """
    Migrate old timestamp format to new per-group format.
    
    Old format: {"0": timestamp, "1": timestamp}
    New format: {"0:group_id": timestamp, "1:group_id": timestamp}
    """
    if not timestamps:
        return timestamps
    
    # Check if already in new format (keys contain ":")
    if any(":" in key for key in timestamps.keys()):
        return timestamps
    
    # Check if in old format (keys are just digits)
    if not all(key.isdigit() for key in timestamps.keys()):
        return timestamps
    
    logger.info("Migrating timestamps from old format to per-group format...")
    
    new_timestamps = {}
    for old_key, timestamp in timestamps.items():
        try:
            idx = int(old_key)
            if idx < len(announcements):
                announcement = announcements[idx]
                target_groups = announcement.get('groups') or config.groups.main
                
                # Expand to all target groups
                for group_id in target_groups:
                    new_key = f"{idx}:{group_id}"
                    new_timestamps[new_key] = timestamp
                    
                logger.debug(f"Migrated key '{old_key}' to {len(target_groups)} group keys")
        except (ValueError, IndexError) as e:
            logger.warning(f"Failed to migrate key '{old_key}': {e}")
    
    logger.info(f"Migration complete: {len(timestamps)} -> {len(new_timestamps)} keys")
    return new_timestamps


def _load_messages(locale: str) -> dict[str, str]:
    """
    Load message definitions from .ftl file.
    
    Messages are defined as:
        msg-key-name =
            Message text here
            Can be multiline
    """
    messages = {}
    
    ftl_path = Path(f"locales/{locale}/announcements.ftl")
    if not ftl_path.exists():
        return messages
    
    content = ftl_path.read_text(encoding="utf-8")
    
    # Parse message blocks (msg-* keys)
    pattern = r'^(msg-[\w-]+)\s*=\s*\n((?:[ \t]+.+\n?)+)'
    
    for match in re.finditer(pattern, content, re.MULTILINE):
        key = match.group(1)
        block = match.group(2)
        
        # Extract message lines (skip @directives and comments)
        lines = []
        for line in block.split('\n'):
            stripped = line.strip()
            if stripped and not stripped.startswith('@') and not stripped.startswith('#'):
                lines.append(line.lstrip())
        
        if lines:
            messages[key] = '\n'.join(lines).strip()
            logger.debug(f"Loaded message: {key}")
    
    logger.info(f"Loaded {len(messages)} message templates")
    return messages


def load_announcements(locale: str = "ru") -> list[dict]:
    """
    Load announcements from .ftl file.
    
    Format in .ftl:
        # Define reusable messages
        msg-report-info =
            Message text here
            Can be multiline
        
        # Use inline message
        announcement-1 =
            Inline message text
            @every: 3600
            @groups: -100123  (optional)
        
        # Or reference a message
        announcement-2 =
            @message: msg-report-info
            @every: 7200
            @groups: -100456
    """
    announcements = []
    
    ftl_path = Path(f"locales/{locale}/announcements.ftl")
    if not ftl_path.exists():
        logger.warning(f"Announcements file not found: {ftl_path}")
        return announcements
    
    content = ftl_path.read_text(encoding="utf-8")
    
    # First load message templates
    messages = _load_messages(locale)
    
    # Parse announcement blocks
    # Match: announcement-N = followed by indented content
    pattern = r'^announcement-\d+\s*=\s*\n((?:[ \t]+.+\n?)+)'
    
    for match in re.finditer(pattern, content, re.MULTILINE):
        block = match.group(1)
        lines = block.split('\n')
        
        message_lines = []
        message_ref = None
        every_min = 3600  # Default 1 hour
        every_max = 3600
        groups = None
        
        for line in lines:
            stripped = line.strip()
            
            if stripped.startswith('@every:'):
                every_str = stripped.replace('@every:', '').strip()
                try:
                    if '-' in every_str:
                        # Range format: 10800-15800
                        parts = every_str.split('-')
                        every_min = int(parts[0].strip())
                        every_max = int(parts[1].strip())
                        if every_min > every_max:
                            every_min, every_max = every_max, every_min
                    else:
                        # Single value
                        every_min = every_max = int(every_str)
                except (ValueError, IndexError):
                    logger.warning(f"Invalid @every value: {stripped}")
            elif stripped.startswith('@groups:'):
                try:
                    groups_str = stripped.replace('@groups:', '').strip()
                    groups = [int(g.strip()) for g in groups_str.split(',') if g.strip()]
                except ValueError:
                    logger.warning(f"Invalid @groups value: {stripped}")
            elif stripped.startswith('@message:'):
                message_ref = stripped.replace('@message:', '').strip()
            elif stripped and not stripped.startswith('#') and not stripped.startswith('@'):
                # Regular message line
                message_lines.append(line.lstrip())
        
        # Resolve message - either from reference or inline
        message = None
        if message_ref:
            if message_ref in messages:
                message = messages[message_ref]
            else:
                logger.warning(f"Message reference not found: {message_ref}")
        elif message_lines:
            message = '\n'.join(message_lines).strip()
        
        if message:
            announcement = {
                'message': message,
                'every_min': every_min,
                'every_max': every_max,
            }
            if groups:
                announcement['groups'] = groups
            announcements.append(announcement)
            
            src = f"ref:{message_ref}" if message_ref else f"inline:{message[:30]}..."
            every_info = f"{every_min}-{every_max}s" if every_min != every_max else f"{every_min}s"
            logger.debug(f"Loaded announcement ({src}, every={every_info})")
    
    logger.info(f"Loaded {len(announcements)} announcements from {ftl_path}")
    return announcements
    
    logger.info(f"Loaded {len(announcements)} announcements from {ftl_path}")
    return announcements


async def send_to_group(message: str, group_id: int) -> bool:
    """
    Send announcement to a single group.
    
    Args:
        message: The message text to send
        group_id: Target group ID
        
    Returns:
        True if sent successfully, False otherwise
    """
    if _bot is None:
        logger.warning("Bot not initialized, skipping announcement")
        return False
    
    try:
        await _bot.send_message(group_id, message)
        logger.debug(f"Announcement sent to {group_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to send announcement to {group_id}: {e}")
        return False


async def run_scheduler() -> None:
    """
    Run the announcement scheduler loop.
    
    Each announcement + group combination has its own independent timer,
    so the same announcement is sent to different groups at different times.
    """
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
    # Key format: "announcement_index:group_id"
    last_sent = _load_timestamps()
    
    # Migrate from old format if needed
    last_sent = _migrate_timestamps(last_sent, _announcements)
    
    # Generate initial random intervals for each announcement:group pair
    # Key format: "announcement_index:group_id"
    next_intervals: dict[str, int] = {}
    
    # Initialize timestamps and intervals for each announcement:group pair
    current_time = time.time()
    for i, announcement in enumerate(_announcements):
        every_min = announcement['every_min']
        every_max = announcement['every_max']
        
        # Get target groups for this announcement
        target_groups = announcement.get('groups') or config.groups.main
        
        for group_id in target_groups:
            key = f"{i}:{group_id}"
            
            # Generate random interval for this pair
            next_intervals[key] = random.randint(every_min, every_max)
            
            if key not in last_sent:
                last_sent[key] = current_time
                logger.debug(f"New announcement #{i+1} for group {group_id} - will send after {next_intervals[key]}s")
    
    _save_timestamps(last_sent)
    logger.info("Announcements initialized with per-group timestamps")
    
    while True:
        try:
            current_time = time.time()
            
            for i, announcement in enumerate(_announcements):
                every_min = announcement['every_min']
                every_max = announcement['every_max']
                message = announcement['message']
                
                # Get target groups for this announcement
                target_groups = announcement.get('groups') or config.groups.main
                
                for group_id in target_groups:
                    key = f"{i}:{group_id}"
                    interval = next_intervals.get(key, every_min)
                    
                    # Check if it's time to send to this group
                    time_since_last = current_time - last_sent.get(key, 0)
                    if time_since_last >= interval:
                        success = await send_to_group(message, group_id)
                        
                        if success:
                            last_sent[key] = current_time
                            _save_timestamps(last_sent)
                            
                            # Generate new random interval for next send
                            next_intervals[key] = random.randint(every_min, every_max)
                            
                            interval_info = f"{every_min}-{every_max}" if every_min != every_max else str(every_min)
                            logger.info(f"Announcement #{i+1} sent to {group_id} (interval: {interval_info}s, next: {next_intervals[key]}s)")
            
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
