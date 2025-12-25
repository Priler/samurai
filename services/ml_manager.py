"""
ML model memory manager.

Automatically unloads ML models after configured TTL to save RAM.
"""
import asyncio
import logging
import time

from config import config
from services import spam, nsfw

logger = logging.getLogger(__name__)

_task: asyncio.Task | None = None


async def _check_and_unload() -> None:
    """Check model TTLs and unload if expired."""
    current_time = time.time()
    
    # check spam model
    if spam.is_loaded():
        last_used = spam.get_last_used()
        ttl_seconds = config.ml.spam_ttl_minutes * 60
        
        if last_used > 0 and (current_time - last_used) > ttl_seconds:
            spam.unload_model()
            logger.info(f"Unloaded spam model (unused for {config.ml.spam_ttl_minutes} min)")
    
    # check NSFW model
    if nsfw.is_loaded():
        last_used = nsfw.get_last_used()
        ttl_seconds = config.ml.nsfw_ttl_minutes * 60
        
        if last_used > 0 and (current_time - last_used) > ttl_seconds:
            nsfw.unload_model()
            logger.info(f"Unloaded NSFW model (unused for {config.ml.nsfw_ttl_minutes} min)")


async def _monitor_loop() -> None:
    """Background loop that periodically checks model TTLs."""
    logger.info(
        f"ML auto-unload enabled: spam={config.ml.spam_ttl_minutes}min, "
        f"nsfw={config.ml.nsfw_ttl_minutes}min, check every {config.ml.check_interval_seconds}s"
    )
    
    while True:
        try:
            await asyncio.sleep(config.ml.check_interval_seconds)
            await _check_and_unload()
        except asyncio.CancelledError:
            logger.info("ML monitor stopped")
            break
        except Exception as e:
            logger.error(f"Error in ML monitor: {e}")


def start_monitor() -> None:
    """Start the background monitor task."""
    global _task
    
    if not config.ml.auto_unload_enabled:
        logger.info("ML auto-unload is disabled")
        return
    
    if _task is not None:
        logger.warning("ML monitor already running")
        return
    
    _task = asyncio.create_task(_monitor_loop())


def stop_monitor() -> None:
    """Stop the background monitor task."""
    global _task
    
    if _task is not None:
        _task.cancel()
        _task = None


def get_status() -> dict:
    """Get current status of ML models."""
    return {
        "spam": {
            "loaded": spam.is_loaded(),
            "last_used": spam.get_last_used(),
            "ttl_minutes": config.ml.spam_ttl_minutes
        },
        "nsfw": {
            "loaded": nsfw.is_loaded(),
            "last_used": nsfw.get_last_used(),
            "ttl_minutes": config.ml.nsfw_ttl_minutes
        },
        "auto_unload_enabled": config.ml.auto_unload_enabled
    }
