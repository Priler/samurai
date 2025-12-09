"""
Error handlers for the bot.
"""
import logging

from aiogram import Router
from aiogram.types import ErrorEvent
from aiogram.exceptions import (
    TelegramUnauthorizedError,
    TelegramBadRequest,
    TelegramAPIError,
    TelegramRetryAfter,
)

router = Router(name="exceptions")


@router.error()
async def error_handler(event: ErrorEvent) -> bool:
    """
    Global error handler. Catches all exceptions within handlers.
    Returns True to stop error propagation.
    """
    exception = event.exception
    update = event.update

    # Can't demote chat creator
    if isinstance(exception, TelegramBadRequest) and "can't demote chat creator" in str(exception):
        logging.debug("Can't demote chat creator")
        return True

    # Message not modified
    if isinstance(exception, TelegramBadRequest) and "message is not modified" in str(exception):
        logging.debug("Message is not modified")
        return True

    # Message can't be deleted
    if isinstance(exception, TelegramBadRequest) and "message can't be deleted" in str(exception):
        logging.debug("Message can't be deleted")
        return True

    # Message to delete not found
    if isinstance(exception, TelegramBadRequest) and "message to delete not found" in str(exception):
        logging.debug("Message to delete not found")
        return True

    # Message text is empty
    if isinstance(exception, TelegramBadRequest) and "message text is empty" in str(exception):
        logging.debug("Message text is empty")
        return True

    # Unauthorized
    if isinstance(exception, TelegramUnauthorizedError):
        logging.info(f"Unauthorized: {exception}")
        return True

    # Invalid query ID
    if isinstance(exception, TelegramBadRequest) and "query is too old" in str(exception):
        logging.debug(f"Invalid query ID: {exception}")
        return True

    # Retry after
    if isinstance(exception, TelegramRetryAfter):
        logging.warning(f"Retry after {exception.retry_after} seconds")
        return True

    # Can't parse entities
    if isinstance(exception, TelegramBadRequest) and "can't parse entities" in str(exception):
        logging.exception(f"Can't parse entities: {exception}\nUpdate: {update}")
        return True

    # General Telegram API error
    if isinstance(exception, TelegramAPIError):
        logging.exception(f"TelegramAPIError: {exception}\nUpdate: {update}")
        return True

    # Unknown exception
    logging.exception(f"Unhandled exception: {exception}\nUpdate: {update}")
    return False
